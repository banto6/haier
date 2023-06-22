import logging

from homeassistant.components.binary_sensor import BinarySensorEntity, BinarySensorDeviceClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.typing import HomeAssistantType

from . import async_register_entity
from .coordinator import DeviceCoordinator
from .entity import HaierAbstractEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistantType, entry: ConfigEntry, async_add_entities) -> None:
    def register(coordinator: DeviceCoordinator, spec: str):
        return HaierSensor(coordinator, spec)

    await async_register_entity(hass, entry, async_add_entities, register, 'binary_sensors')


class HaierSensor(HaierAbstractEntity, BinarySensorEntity):

    def __init__(self, coordinator: DeviceCoordinator, spec: dict):
        super().__init__(coordinator, spec)
        self._attr_device_class = BinarySensorDeviceClass.WINDOW

    def _update_value(self):
        self._attr_is_on = self.coordinator.data[self._spec['key']]



