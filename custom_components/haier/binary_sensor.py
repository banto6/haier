import logging

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.helpers.typing import HomeAssistantType

from . import async_register_entity
from .core.attribute import HaierAttribute
from .core.device import HaierDevice
from .entity import HaierAbstractEntity
from .helpers import try_read_as_bool

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistantType, entry: ConfigEntry, async_add_entities) -> None:
    await async_register_entity(
        hass,
        entry,
        async_add_entities,
        Platform.BINARY_SENSOR,
        lambda device, attribute: HaierBinarySensor(device, attribute)
    )


class HaierBinarySensor(HaierAbstractEntity, BinarySensorEntity):

    def __init__(self, device: HaierDevice, attribute: HaierAttribute):
        super().__init__(device, attribute)

    def _update_value(self):
        try:
            self._attr_is_on = try_read_as_bool(self._attributes_data[self._attribute.key])
        except ValueError:
            _LOGGER.exception('entity [{}] read value failed'.format(self._attr_unique_id))
            self._attr_available = False

