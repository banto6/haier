import logging
from datetime import timedelta

from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import DOMAIN
from .haier import HaierClient

_LOGGER = logging.getLogger(__name__)


class DeviceCoordinator(DataUpdateCoordinator):

    def __init__(self, hass, client: HaierClient, device):
        super().__init__(
            hass,
            _LOGGER,
            name='Haier Device [' + device['deviceId'] + ']',
            update_interval=timedelta(seconds=15),
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
