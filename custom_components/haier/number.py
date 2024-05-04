import logging

from homeassistant.components.number import NumberEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from . import async_register_entity
from .core.attribute import HaierAttribute
from .core.device import HaierDevice
from .entity import HaierAbstractEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities) -> None:
    await async_register_entity(
        hass,
        entry,
        async_add_entities,
        Platform.NUMBER,
        lambda device, attribute: HaierNumber(device, attribute)
    )


class HaierNumber(HaierAbstractEntity, NumberEntity):

    def __init__(self, device: HaierDevice, attribute: HaierAttribute):
        super().__init__(device, attribute)

    def _update_value(self):
        self._attr_native_value = self._attributes_data[self._attribute.key]

    def set_native_value(self, value: float) -> None:
        self._send_command({
            self._attribute.key: value
        })



