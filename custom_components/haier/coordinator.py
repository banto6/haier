import json
import logging
import os
from datetime import timedelta

from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .core.device import HaierDevice

_LOGGER = logging.getLogger(__name__)


class DeviceCoordinator(DataUpdateCoordinator):

    def __init__(self, hass, device: HaierDevice):
        super().__init__(
            hass,
            _LOGGER,
            name='Haier Device [' + device.id + ']',
            update_interval=timedelta(seconds=15),
        )

        self._device = device

    async def _async_update_data(self):
        if self._device.is_virtual:
            with open(os.path.dirname(__file__) + '/virtual_devices/{}.json'.format(self._device.id)) as fp:
                return json.load(fp)['data']

        data = await self._device.read_attributes()

        _LOGGER.debug('设备[{}]已获取到最新状态数据: {}'.format(self._device.id, json.dumps(data)))

        return data
