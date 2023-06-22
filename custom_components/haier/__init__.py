import logging
import os
from typing import List

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_USERNAME, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.helpers.typing import HomeAssistantType

from .const import PLATFORMS, DOMAIN
from .coordinator import DeviceCoordinator
from .haier import HaierClient, Session

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    hass.data.setdefault(DOMAIN, {})

    client = HaierClient(Session({'uhome_access_token': await get_token(hass, entry, True)}))

    devices = await client.get_devices()
    _LOGGER.debug('共获取到{}个设备'.format(len(devices)))

    coordinators = []
    for device in devices:
        try:
            coordinator = await new_device_coordinator(hass, client, device)
            coordinators.append(coordinator)
        except Exception:
            _LOGGER.exception('设备[{}]初始化失败', device['deviceId'])

    hass.data[DOMAIN]['coordinators'] = coordinators

    for platform in PLATFORMS:
        hass.async_create_task(
            hass.config_entries.async_forward_entry_setup(entry, platform)
        )

    return True


async def new_device_coordinator(hass, client: HaierClient, device):
    device['net'] = await client.get_net_quality_by_device(device['deviceId'])

    device_profile = os.path.dirname(__file__) + '/device_profiles/' + device['wifiType'] + '.json'
    _LOGGER.debug('device_profile: {}'.format(device_profile))
    # if os.path.exists(device_profile):
    #     with open(device_profile, 'r') as fp:
    #         device['config'] = json.load(fp)
    #
    #     _LOGGER.debug('设备[{}]已使用本地描述文件'.format(device['deviceId']))
    # else:
    device['config'] = await client.get_hardware_config(device['wifiType'])
        # _LOGGER.debug('设备[{}]已使用云端描述文件'.format(device['deviceId']))

    coordinator = DeviceCoordinator(hass, client, device)
    await coordinator.async_config_entry_first_refresh()

    return coordinator


async def async_register_entity(hass: HomeAssistantType, entry: ConfigEntry, async_add_entities, platform,
                                spec_attr) -> None:
    coordinators: List[DeviceCoordinator] = hass.data[DOMAIN]['coordinators']
    entities = []

    for coordinator in coordinators:
        for spec in getattr(coordinator, spec_attr):
            if spec['key'] not in coordinator.data.keys():
                _LOGGER.warning('{} not found in the data source'.format(spec['key']))
                continue

            entities.append(platform(coordinator, spec))

    async_add_entities(entities)


async def get_token(hass: HomeAssistantType, entry: ConfigEntry, force_refresh=False):
    store = Store(hass, 1, 'haier/{}/token'.format(entry.data[CONF_USERNAME]))
    token = await store.async_load() or None

    if token is None or force_refresh:
        session = await HaierClient.get_session(entry.data[CONF_USERNAME], entry.data[CONF_PASSWORD])
        token = session.get_token()

        _LOGGER.debug('已获取到新token: {}'.format(token))

        await store.async_save(token)

    return token



