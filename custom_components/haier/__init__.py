import logging
import time
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntry
from homeassistant.helpers.event import async_track_time_interval

from .const import DOMAIN, SUPPORTED_PLATFORMS, FILTER_TYPE_EXCLUDE, FILTER_TYPE_INCLUDE
from .core.client import HaierClient, HaierClientException, TokenInfo
from .core.config import AccountConfig, DeviceFilterConfig, EntityFilterConfig
from .core.device_gateway import HaierDeviceGateway

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    hass.data.setdefault(DOMAIN, {
        'devices': [],
        'cancel_token_updater': None,
        'gateway_task': None,
    })

    # 定时更新token
    hass.data[DOMAIN]['cancel_token_updater'] = await token_updater(hass, entry)

    account_cfg = AccountConfig(hass, entry)
    client = HaierClient(hass, account_cfg.client_id, account_cfg.token)

    devices = await client.get_devices()
    _LOGGER.info('共获取到{}个设备'.format(len(devices)))
    hass.data[DOMAIN]['devices'] = devices

    # 启动网关
    gateway = HaierDeviceGateway(hass, client, account_cfg.token)
    hass.data[DOMAIN]['gateway_task'] = hass.async_create_background_task(
        gateway.connect(devices),
        'haier-gateway'
    )

    await hass.config_entries.async_forward_entry_setups(entry, SUPPORTED_PLATFORMS)

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
        client = HaierClient(hass, cfg.client_id, cfg.token)

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
        except Exception:
            _LOGGER.exception('token update failed')

    # 手动执行一次更新
    await try_update_token()

    # 每1小时检查一次token有效性，若token刷新则重载集成
    return async_track_time_interval(hass, task, timedelta(hours=1))

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    for platform in SUPPORTED_PLATFORMS:
        if not await hass.config_entries.async_forward_entry_unload(entry, platform):
            return False

    # 停止token更新
    if hass.data[DOMAIN]['cancel_token_updater']:
        hass.data[DOMAIN]['cancel_token_updater']()
        _LOGGER.info('token updater stopped')

    # 断开网关
    if hass.data[DOMAIN]['gateway_task']:
        hass.data[DOMAIN]['gateway_task'].cancel()
        _LOGGER.info('gateway task cancelled')

    del hass.data[DOMAIN]

    return True


async def entry_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    _LOGGER.info('reload haier integration...')
    await hass.config_entries.async_reload(entry.entry_id)

async def async_remove_config_entry_device(hass: HomeAssistant, config: ConfigEntry, device: DeviceEntry) -> bool:
    device_id = list(device.identifiers)[0][1]

    _LOGGER.info('Device [{}] removing...'.format(device_id))

    for device in hass.data[DOMAIN]['devices']:
        if device.id.lower() == device_id:
            target_device = device
            break
    else:
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
    entities = []
    for device in hass.data[DOMAIN]['devices']:
        if DeviceFilterConfig.is_skip(hass, entry, device.id):
            continue

        for attribute in device.attributes:
            if attribute.platform != platform:
                continue

            if EntityFilterConfig.is_skip(hass, entry, device.id, attribute.key):
                continue

            entities.append(setup(device, attribute))

    async_add_entities(entities)
