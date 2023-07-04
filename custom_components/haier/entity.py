import asyncio
import logging
from abc import ABC, abstractmethod

from homeassistant.core import callback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import DOMAIN
from .coordinator import DeviceCoordinator

_LOGGER = logging.getLogger(__name__)


class HaierAbstractEntity(CoordinatorEntity, ABC):

    _spec: None

    def __init__(self, coordinator: DeviceCoordinator, spec: dict):
        super().__init__(coordinator, context=coordinator.device.id)
        self._attr_unique_id = '{}.{}_{}'.format(DOMAIN, coordinator.device.id, spec['key']).lower()
        self.entity_id = self._attr_unique_id

        self._attr_name = spec['display_name']
        self._attr_device_info = coordinator.device_info
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
