import logging

from homeassistant.components.number import NumberEntity, NumberDeviceClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.typing import HomeAssistantType

from . import async_register_entity
from .coordinator import DeviceCoordinator
from .entity import HaierAbstractEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistantType, entry: ConfigEntry, async_add_entities) -> None:
    def register(coordinator: DeviceCoordinator, spec: str):
        return HaierNumber(coordinator, spec)

    await async_register_entity(hass, entry, async_add_entities, register, 'numbers')


class HaierNumber(HaierAbstractEntity, NumberEntity):

    def __init__(self, coordinator: DeviceCoordinator, spec: str):
        super().__init__(coordinator, spec)
        self._attr_native_min_value = spec['minValue']
        self._attr_native_max_value = spec['maxValue']
        self._attr_native_step = spec['step']
        self._attr_device_class = NumberDeviceClass.TEMPERATURE

    def _update_value(self):
        self._attr_native_value = self.coordinator.data[self._spec['key']]

    def set_native_value(self, value: float) -> None:
        self._send_command({
            self._spec['key']: value
        })


