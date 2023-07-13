import logging

from homeassistant.components.number import NumberEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.helpers.typing import HomeAssistantType

from . import async_register_entity
from .coordinator import DeviceCoordinator
from .core.attribute import HaierAttribute
from .core.device import HaierDevice
from .entity import HaierAbstractEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistantType, entry: ConfigEntry, async_add_entities) -> None:
    await async_register_entity(
        hass,
        entry,
        async_add_entities,
        Platform.NUMBER,
        lambda coordinator, device, attribute: HaierNumber(coordinator, device, attribute)
    )


class HaierNumber(HaierAbstractEntity, NumberEntity):

    def __init__(self, coordinator: DeviceCoordinator, device: HaierDevice, attribute: HaierAttribute):
        super().__init__(coordinator, device, attribute)

    def _update_value(self):
        self._attr_native_value = self.coordinator.data[self._attribute.key]

    def set_native_value(self, value: float) -> None:
        self._send_command({
            self._attribute.key: value
        })



