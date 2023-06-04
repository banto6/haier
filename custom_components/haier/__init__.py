import json
import logging
import os
from datetime import timedelta

from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.typing import HomeAssistantType
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from .const import PLATFORMS, DOMAIN
from .haier import HaierClient, Session

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistantType, entry: ConfigEntry):
    hass.data.setdefault(DOMAIN, {})

    coordinators = []

    client = HaierClient(Session({'uhome_access_token': entry.data['token']}))
    devices = await client.get_devices()

    _LOGGER.debug('共获取到{}个设备'.format(len(devices)))

    for device in devices:
        coordinator = await new_device_coordinator(hass, client, device)
        coordinators.append(coordinator)

    hass.data[DOMAIN]['coordinators'] = coordinators

    for platform in PLATFORMS:
        hass.async_create_task(
            hass.config_entries.async_forward_entry_setup(entry, platform)
        )

    return True


async def new_device_coordinator(hass, client: HaierClient, device):
    device['net'] = await client.get_net_quality_by_device(device['deviceId'])

    device_profiles = './device_profiles/'+ device['wifiType'] + '.json'
    if os.path.exists(device_profiles):
        with open(device_profiles, 'r') as fp:
            device['config'] = json.load(fp)

        _LOGGER.debug('设备[{}]已使用本地描述文件'.format(device['deviceId']))
    else:
        device['config'] = await client.get_hardware_config(device['wifiType'])
        _LOGGER.debug('设备[{}]已使用云端描述文件'.format(device['deviceId']))

    coordinator = DeviceCoordinator(hass, client, device)
    await coordinator.async_config_entry_first_refresh()

    return coordinator


class DeviceCoordinator(DataUpdateCoordinator):

    def __init__(self, hass, client: HaierClient, device):
        super().__init__(
            hass,
            _LOGGER,
            name='Haier Device [' + device['deviceId'] + ']',
            update_interval=timedelta(seconds=5),
        )

        self._client = client
        self._device = device
        self._device_info = DeviceInfo(
            identifiers={(DOMAIN, device['deviceId'].lower())},
            name=device['deviceName'],
            manufacturer='haier',
            model=device['productNameT'],
            sw_version=device['net']['hardwareVers']
        )

    @property
    def client(self):
        return self._client

    @property
    def device_id(self):
        return self._device['deviceId']

    @property
    def device(self):
        return self._device_info

    @property
    def sensors(self):
        sensors = []
        for config_property in self._device['config']['Property']:
            # 跳过已禁用的项目
            if 'disable' in config_property and config_property['disable']:
                continue

            # 可写表示可操作，因为不应该归为传感器
            if config_property['writable']:
                continue

            sensors.append({
                'key': config_property['name'],
                'device_class': SensorDeviceClass.TEMPERATURE,
                'native_unit_of_measurement': ''
            })

        return sensors

    @property
    def numbers(self):
        numbers = []
        for config_property in self._device['config']['Property']:
            # 跳过已禁用的项目
            if 'disable' in config_property and config_property['disable']:
                continue

            # 可写表示可操作，因为不应该归为传感器
            if config_property['writable'] and config_property['type'] in ['int', 'double']:
                numbers.append({
                    'key': config_property['name'],
                    'minValue': config_property['variants']['minValue'],
                    'maxValue': config_property['variants']['maxValue'],
                    'step': config_property['variants']['step'],
                })

        return numbers

    @property
    def selects(self):
        selects = []
        for config_property in self._device['config']['Property']:
            # 跳过已禁用的项目
            if 'disable' in config_property and config_property['disable']:
                continue

            # 可写表示可操作，因此不应该归为传感器
            if config_property['writable'] and config_property['type'] in ['enum']:
                selects.append({
                    'key': config_property['name'],
                    'options': [{'value': item['stdValue'], 'label': item['description']} for item in
                                config_property['variants']]
                })

        return selects

    async def _async_update_data(self):
        return await self._client.get_last_report_status_by_device(self._device['deviceId'])
