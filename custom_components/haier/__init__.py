import glob
import json
import logging
import os
from typing import List

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_USERNAME, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import HomeAssistantType

from .const import PLATFORMS, DOMAIN, CONF_ACCOUNT, CONF_DEVICE_FILTER, CONF_FILTER_TYPE, CONF_TARGET_DEVICES
from .coordinator import DeviceCoordinator
from .haier import HaierClient, HaierClientException, HaierDevice

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    hass.data.setdefault(DOMAIN, {})

    client = HaierClient(entry.data[CONF_ACCOUNT][CONF_USERNAME], entry.data[CONF_ACCOUNT][CONF_PASSWORD])
    await client.try_login()

    devices = (await client.get_devices()) + get_virtual_devices()
    hass.data[DOMAIN]['devices'] = devices
    _LOGGER.debug('共获取到{}个设备'.format(len(devices)))

    filtered_devices = get_filtered_devices(entry, devices)
    _LOGGER.debug('经过过滤后共获取到{}个设备'.format(len(filtered_devices)))

    coordinators = []
    for device in filtered_devices:
        try:
            sw_version = 'N/A'
            if not device.is_virtual:
                sw_version = (await client.get_net_quality_by_device(device.id))['hardwareVers']

            specs = await client.get_hardware_config(device.wifi_type)
            coordinator = DeviceCoordinator(hass, client, device, sw_version, specs)
            await coordinator.async_config_entry_first_refresh()
            coordinators.append(coordinator)
        except Exception:
            _LOGGER.exception('设备[{}]初始化失败'.format(device.id))

    hass.data[DOMAIN]['coordinators'] = coordinators

    for platform in PLATFORMS:
        hass.async_create_task(
            hass.config_entries.async_forward_entry_setup(entry, platform)
        )

    entry.async_on_unload(entry.add_update_listener(entry_update_listener))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    for platform in PLATFORMS:
        if not await hass.config_entries.async_forward_entry_unload(entry, platform):
            return False

    hass.data[DOMAIN] = {}

    return True


async def entry_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update."""
    _LOGGER.debug('reload.....')
    await hass.config_entries.async_reload(entry.entry_id)


async def async_migrate_entry(hass, config_entry: ConfigEntry):
    """Migrate old entry."""
    _LOGGER.info("Migrating from version %s", config_entry.version)

    if config_entry.version == 1:
        config_entry.version = 2
        hass.config_entries.async_update_entry(config_entry, data={
            CONF_ACCOUNT: dict(config_entry.data)
        })

    _LOGGER.info("Migration to version %s successful", config_entry.version)

    return True


def get_filtered_devices(entry: ConfigEntry, devices: List[HaierDevice]) -> List[HaierDevice]:
    cfg = entry.data.get(CONF_DEVICE_FILTER, {})
    if not cfg:
        _LOGGER.debug('未配置设备过滤规则')
        return devices

    if cfg[CONF_FILTER_TYPE] == 'exclude':
        return [device for device in devices if device.id not in cfg[CONF_TARGET_DEVICES]]
    else:
        return [device for device in devices if device.id in cfg[CONF_TARGET_DEVICES]]


def get_virtual_devices() -> List[HaierDevice]:
    target_folder = os.path.dirname(__file__) + '/virtual_devices'
    if not os.path.exists(target_folder):
        return []

    devices = []
    for file in glob.glob(target_folder + '/*.json'):
        with open(file, 'r') as fp:
            device = json.load(fp)
            device['virtual'] = True
            devices.append(HaierDevice(device))

    return devices


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
