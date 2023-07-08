import glob
import json
import logging
import os
from typing import List

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntry
from homeassistant.helpers.typing import HomeAssistantType

from .const import DOMAIN, SUPPORTED_PLATFORMS, FILTER_TYPE_EXCLUDE, FILTER_TYPE_INCLUDE
from .coordinator import DeviceCoordinator
from .core.config import AccountConfig, DeviceFilterConfig, EntityFilterConfig
from .haier import HaierClient, HaierClientException, HaierDevice

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    hass.data.setdefault(DOMAIN, {})

    account_cfg = AccountConfig(hass, entry)
    client = HaierClient(account_cfg.username, account_cfg.password)
    hass.data[DOMAIN]['client'] = client

    await client.try_login()

    devices = (await client.get_devices()) + get_virtual_devices()
    hass.data[DOMAIN]['devices'] = devices
    _LOGGER.debug('共获取到{}个设备'.format(len(devices)))

    filtered_devices = get_filtered_devices(hass, entry, devices)
    _LOGGER.debug('经过过滤后共获取到{}个设备'.format(len(filtered_devices)))

    coordinators = []
    for device in filtered_devices:
        _LOGGER.debug('Device Info: {}'.format(device.__dict__))
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

    for platform in SUPPORTED_PLATFORMS:
        hass.async_create_task(
            hass.config_entries.async_forward_entry_setup(entry, platform)
        )

    entry.async_on_unload(entry.add_update_listener(entry_update_listener))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    for platform in SUPPORTED_PLATFORMS:
        if not await hass.config_entries.async_forward_entry_unload(entry, platform):
            return False

    hass.data[DOMAIN] = {}

    return True


async def entry_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    _LOGGER.debug('reload.....')
    await hass.config_entries.async_reload(entry.entry_id)


async def async_migrate_entry(hass, config_entry: ConfigEntry):
    _LOGGER.info("Migrating from version %s", config_entry.version)

    if config_entry.version == 1:
        config_entry.version = 2
        hass.config_entries.async_update_entry(config_entry, data={
            'account': dict(config_entry.data)
        })

    _LOGGER.info("Migration to version %s successful", config_entry.version)

    return True


def get_filtered_devices(hass, entry: ConfigEntry, devices: List[HaierDevice]) -> List[HaierDevice]:
    cfg = DeviceFilterConfig(hass, entry)

    if cfg.filter_type == FILTER_TYPE_EXCLUDE:
        return [device for device in devices if device.id not in cfg.target_devices]
    else:
        return [device for device in devices if device.id in cfg.target_devices]


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

    cfg = EntityFilterConfig(hass, entry)

    entities = []
    for coordinator in coordinators:
        filter_type = cfg.get_filter_type(coordinator.device.id)
        target_entities = cfg.get_target_entities(coordinator.device.id)

        for spec in getattr(coordinator, spec_attr):
            if spec['key'] not in coordinator.data.keys():
                _LOGGER.warning('{} not found in the data source'.format(spec['key']))
                continue

            if filter_type == FILTER_TYPE_EXCLUDE and spec['key'] in target_entities:
                continue

            if filter_type == FILTER_TYPE_INCLUDE and spec['key'] not in target_entities:
                continue

            entities.append(platform(coordinator, spec))

    async_add_entities(entities)
