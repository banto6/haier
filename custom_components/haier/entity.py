import asyncio
import logging
from abc import ABC, abstractmethod

from homeassistant.core import callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import DOMAIN
from .coordinator import DeviceCoordinator
from .core.attribute import HaierAttribute
from .core.device import HaierDevice

_LOGGER = logging.getLogger(__name__)


class HaierAbstractEntity(CoordinatorEntity, ABC):

    _device: HaierDevice

    _attribute: HaierAttribute

    def __init__(self, coordinator: DeviceCoordinator, device: HaierDevice, attribute: HaierAttribute):
        super().__init__(coordinator, context=device.id)
        self._attr_unique_id = '{}.{}_{}'.format(DOMAIN, device.id, attribute.key).lower()
        self.entity_id = self._attr_unique_id

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device.id.lower())},
            name=device.name,
            manufacturer='海尔',
            model=device.product_name,
            sw_version=device.sw_version
        )

        self._attr_name = attribute.display_name
        for key, value in attribute.options.items():
            setattr(self, '_attr_' + key, value)

        self._device = device
        self._attribute = attribute
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
            await self._device.write_attributes(args)
            self._update_value()
            self.async_write_ha_state()

        asyncio.run(execute())

    @abstractmethod
    def _update_value(self):
        pass
