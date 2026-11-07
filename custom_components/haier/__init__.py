import logging
import time
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.device_registry import DeviceEntry
from homeassistant.helpers.event import async_track_time_interval

from .const import DOMAIN, SUPPORTED_PLATFORMS, FILTER_TYPE_EXCLUDE, FILTER_TYPE_INCLUDE
from .core.client import HaierClient, HaierClientException
from .core.config import (
    AccountConfig,
    DeviceFilterConfig,
    EntityFilterConfig,
    PreferencesConfig,
)
from .core.device_gateway import HaierDeviceGateway
from .core.migration import CONFIG_ENTRY_MIGRATOR
from .core.runtime import HaierRuntimeData
from .services import async_setup_services, async_unload_services

_LOGGER = logging.getLogger(__name__)


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """迁移旧版配置。"""
    return CONFIG_ENTRY_MIGRATOR.migrate(hass, entry)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    # 定时更新token
    try:
        cancel_token_updater = await token_updater(hass, entry)
    except HaierClientException as err:
        raise ConfigEntryNotReady('Haier authentication failed') from err

    account_cfg = AccountConfig(hass, entry)
    preferences_cfg = PreferencesConfig(hass, entry)
    client = HaierClient(hass, account_cfg.client_id, account_cfg.token, account_cfg.app_source)

    devices = await client.get_devices()
    _LOGGER.info('共获取到{}个设备'.format(len(devices)))

    gateway = HaierDeviceGateway(hass, client, account_cfg.token, entry.entry_id)

    # 每个条目一份运行时状态。原先放在 hass.data[DOMAIN] 里，多个条目会互相
    # 覆盖设备列表与任务槽位，卸载任一条目还会把整块数据删掉。
    runtime = HaierRuntimeData(
        entry_id=entry.entry_id,
        client=client,
        devices=devices,
        gateway=gateway,
        ignore_device_offline=preferences_cfg.ignore_device_offline,
        cancel_token_updater=cancel_token_updater,
    )
    entry.runtime_data = runtime

    await hass.config_entries.async_forward_entry_setups(entry, SUPPORTED_PLATFORMS)

    # 实体完成注册后再启动网关，避免初始快照事件无人监听。
    runtime.gateway_task = hass.async_create_background_task(
        gateway.connect(devices),
        'haier-gateway-{}'.format(entry.entry_id)
    )

    async_setup_services(hass)

    entry.async_on_unload(entry.add_update_listener(entry_update_listener))

    return True

async def token_updater(hass: HomeAssistant, entry: ConfigEntry):
    """
    token更新器
    :param hass:
    :param entry:
    :return:
    """
    async def try_update_token():
        """
        尝试刷新token，刷新成功返回True，如refresh_token无效则会抛出异常
        :return:
        """
        _LOGGER.debug("try update token...")

        cfg = AccountConfig(hass, entry)
        client = HaierClient(hass, cfg.client_id, cfg.token, cfg.app_source)

        token_valid = True
        try:
            await client.get_user_info()
        except HaierClientException:
            token_valid = False

        # token有效且里过期时间大于1天时不更新token
        if token_valid and cfg.expires_at - int(time.time()) > 86400:
            return False

        token_info = await client.refresh_token(cfg.refresh_token)
        cfg.token = token_info.token
        cfg.refresh_token = token_info.refresh_token
        cfg.expires_at = int(time.time()) + token_info.expires_in
        cfg.save()

        return True

    async def task(now):
        try:
            if await try_update_token():
                _LOGGER.info('token refreshed, reload integration...')
                await hass.config_entries.async_reload(entry.entry_id)
            else:
                _LOGGER.debug('token is valid')
        except HaierClientException:
            _LOGGER.warning('token refresh authentication failed')
        except Exception:
            _LOGGER.exception('token update failed')

    # 手动执行一次更新
    await try_update_token()

    # 每1小时检查一次token有效性，若token刷新则重载集成
    return async_track_time_interval(hass, task, timedelta(hours=1))

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    if not await hass.config_entries.async_unload_platforms(entry, SUPPORTED_PLATFORMS):
        return False

    runtime: HaierRuntimeData | None = getattr(entry, 'runtime_data', None)
    if runtime is not None:
        # 停止token更新
        if runtime.cancel_token_updater:
            runtime.cancel_token_updater()
            _LOGGER.info('token updater stopped')

        # 断开网关
        if runtime.gateway_task:
            runtime.gateway_task.cancel()
            _LOGGER.info('gateway task cancelled')

    # 服务是 domain 级的，只在最后一个条目卸载时注销，
    # 否则另一个条目还在跑却调不到 send_raw_command
    if not [
        item for item in hass.config_entries.async_entries(DOMAIN)
        if item.entry_id != entry.entry_id
    ]:
        async_unload_services(hass)

    return True


async def entry_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    _LOGGER.info('reload haier integration...')
    await hass.config_entries.async_reload(entry.entry_id)

async def async_remove_config_entry_device(hass: HomeAssistant, config: ConfigEntry, device: DeviceEntry) -> bool:
    device_id = list(device.identifiers)[0][1]

    _LOGGER.info('Device [{}] removing...'.format(device_id))

    runtime: HaierRuntimeData | None = getattr(config, 'runtime_data', None)
    target_device = None
    for item in runtime.devices if runtime is not None else []:
        if item.id.lower() == device_id.lower():
            target_device = item
            break

    if target_device is None:
        _LOGGER.error('Device [{}] not found'.format(device_id))
        return False

    cfg = DeviceFilterConfig(hass, config)
    if cfg.filter_type == FILTER_TYPE_EXCLUDE:
        cfg.add_device(target_device.id)
    else:
        cfg.remove_device(target_device.id)

    cfg.save()

    _LOGGER.info('Device [{}] removed'.format(device_id))

    return True

async def async_register_entity(hass: HomeAssistant, entry: ConfigEntry, async_add_entities, platform, setup) -> None:
    runtime: HaierRuntimeData = entry.runtime_data
    entities = []
    for device in runtime.devices:
        if DeviceFilterConfig.is_skip(hass, entry, device.id):
            continue

        for attribute in device.attributes:
            if attribute.platform != platform:
                continue

            if EntityFilterConfig.is_skip(hass, entry, device.id, attribute.key):
                continue

            entities.append(setup(device, attribute, runtime))

    async_add_entities(entities)
