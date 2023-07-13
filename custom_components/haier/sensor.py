import logging

from homeassistant.components.sensor import SensorEntity
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
        Platform.SENSOR,
        lambda coordinator, device, attribute: HaierSensor(coordinator, device, attribute)
    )


class HaierSensor(HaierAbstractEntity, SensorEntity):

    def __init__(self, coordinator: DeviceCoordinator, device: HaierDevice, attribute: HaierAttribute):
        super().__init__(coordinator, device, attribute)

    def _update_value(self):
        comparison_table = self._attribute.ext.get('value_comparison_table', {})

        value = self.coordinator.data[self._attribute.key]
        self._attr_native_value = comparison_table[value] if value in comparison_table else value





