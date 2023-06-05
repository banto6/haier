import asyncio
import logging
from abc import ABC, abstractmethod

from homeassistant.core import callback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import DeviceCoordinator

_LOGGER = logging.getLogger(__name__)


class HaierAbstractEntity(CoordinatorEntity, ABC):

    _spec: None

    def __init__(self, coordinator: DeviceCoordinator, spec: str):
        super().__init__(coordinator, context=coordinator.device_id)
        self._attr_unique_id = '{}_{}'.format(coordinator.device_id, spec['key']).lower()
        _LOGGER.debug('unique_id: {}'.format(self._attr_unique_id))

        self._attr_name = spec['key']
        self._attr_device_info = coordinator.device
        self._spec = spec
        self._update_value()

    @callback
    def _handle_coordinator_update(self) -> None:
        self._update_value()
        self.async_write_ha_state()

    def _send_command(self, args):
        """
        发送控制命令
        :param args:
        :return:
        """
        async def execute():
            await self.coordinator.client.send_command(self.coordinator.device_id, args)
            self._update_value()
            self.async_write_ha_state()

        asyncio.run(execute())

    @abstractmethod
    def _update_value(self):
        pass
