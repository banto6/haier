import logging
import time
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.device_registry import DeviceEntry
from homeassistant.helpers.event import async_track_time_interval

from .const import DOMAIN, SUPPORTED_PLATFORMS, FILTER_TYPE_EXCLUDE, FILTER_TYPE_INCLUDE, TOKEN_BUFFER_INTERVAL
from .core.client import APP_SOURCE_OAUTH, HaierClient, HaierClientException, TokenInfo
from .core.config import (
    AccountConfig,
    DeviceFilterConfig,
    EntityFilterConfig,
    PreferencesConfig,
)
from .core.device_gateway import HaierDeviceGateway
from .core.migration import CONFIG_ENTRY_MIGRATOR
from .services import async_setup_services, async_unload_services

_LOGGER = logging.getLogger(__name__)

# 网页授权 token 的刷新节流：entry_id -> 上次刷新时间戳。
# 防止"刷新拿到的有效期比缓冲窗口还短"时陷入 刷新->重载->刷新 的死循环。
_OAUTH_REFRESHED_AT: dict[str, int] = {}
_OAUTH_REFRESH_GUARD_SECONDS = 300


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """迁移旧版配置。"""
    return CONFIG_ENTRY_MIGRATOR.migrate(hass, entry)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    hass.data.setdefault(DOMAIN, {
        'devices': [],
        'cancel_token_updater': None,
        'gateway_task': None,
        'gateway_connected': False,
    })

    # 定时更新token
    try:
        hass.data[DOMAIN]['cancel_token_updater'] = await token_updater(hass, entry)
    except HaierClientException as err:
        raise ConfigEntryNotReady('Haier authentication failed') from err

    account_cfg = AccountConfig(hass, entry)
    preferences_cfg = PreferencesConfig(hass, entry)
    client = HaierClient(hass, account_cfg.client_id, account_cfg.token, account_cfg.app_source)

    # 是否忽略设备离线状态，供实体在收到离线事件时判断是否保留最后状态
    hass.data[DOMAIN]['ignore_device_offline'] = preferences_cfg.ignore_device_offline

    devices = await client.get_devices()
    _LOGGER.info('共获取到{}个设备'.format(len(devices)))
    hass.data[DOMAIN]['devices'] = devices

    await hass.config_entries.async_forward_entry_setups(entry, SUPPORTED_PLATFORMS)

    # 实体完成注册后再启动网关，避免初始快照事件无人监听。
    gateway = HaierDeviceGateway(hass, client, account_cfg.token)
    hass.data[DOMAIN]['gateway_task'] = hass.async_create_background_task(
        gateway.connect(devices),
        'haier-gateway'
    )

    async_setup_services(hass)

    entry.async_on_unload(entry.add_update_listener(entry_update_listener))

    return True

async def _try_update_oauth_token(hass: HomeAssistant, entry: ConfigEntry, cfg: AccountConfig) -> bool:
    """
    刷新网页授权（OAuth2）账户的token，刷新成功返回True
    这类token由 ha.haier.net 的OAuth2端点签发，与 zj 网关不互通，
    刷新必须回到签发端点，且clientId须与授权时一致（即 account.client_id）
    :param hass:
    :param entry:
    :param cfg:
    :return:
    """
    now = int(time.time())
    remaining = cfg.expires_at - now

    # 剩余有效期大于缓冲窗口时不做无谓刷新
    if remaining > TOKEN_BUFFER_INTERVAL:
        return False

    # 刚刷新过就不再刷，避免刷新结果的有效期过短时反复重载
    if now - _OAUTH_REFRESHED_AT.get(entry.entry_id, 0) < _OAUTH_REFRESH_GUARD_SECONDS:
        _LOGGER.debug('web-auth token refreshed recently, skip')
        return False

    client = HaierClient(hass, cfg.client_id, cfg.token, cfg.app_source)

    try:
        token_info = await client.oauth_refresh_token(cfg.refresh_token)
    except HaierClientException as err:
        # 已过期且刷新失败：refresh_token 已失效，只能重新授权。
        # 交给 HA 拉起 reauth 流程，否则条目会一直用死 token 空转。
        if remaining <= 0:
            raise ConfigEntryAuthFailed(
                'web-auth token expired, re-authorization required'
            ) from err

        # 只是提前续期没成功，现有token仍然可用，下一轮再试，不打断集成
        _LOGGER.warning('web-auth token refresh failed, keep current token: %s', err)
        return False

    cfg.token = token_info.token
    cfg.refresh_token = token_info.refresh_token
    cfg.expires_at = int(time.time()) + token_info.expires_in
    cfg.save()
    _OAUTH_REFRESHED_AT[entry.entry_id] = now

    _LOGGER.info('web-auth token refreshed, expires_in={}'.format(token_info.expires_in))

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

        # 网页授权账户的token归属 ha 网关，不能用 zj 的账号接口和刷新接口
        if cfg.app_source == APP_SOURCE_OAUTH:
            return await _try_update_oauth_token(hass, entry, cfg)

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
        except ConfigEntryAuthFailed:
            # 续期失败且 token 已过期：让用户重新授权，别静默空转
            _LOGGER.warning('token expired, starting re-authorization')
            entry.async_start_reauth(hass)
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

    # 停止token更新
    if hass.data[DOMAIN]['cancel_token_updater']:
        hass.data[DOMAIN]['cancel_token_updater']()
        _LOGGER.info('token updater stopped')

    # 断开网关
    if hass.data[DOMAIN]['gateway_task']:
        hass.data[DOMAIN]['gateway_task'].cancel()
        _LOGGER.info('gateway task cancelled')

    async_unload_services(hass)

    # 刷新节流是按 entry 记的，条目卸载后这条记录没有意义了
    _OAUTH_REFRESHED_AT.pop(entry.entry_id, None)

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
