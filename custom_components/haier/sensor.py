import logging

from homeassistant.components.sensor import SensorEntity, SensorDeviceClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.typing import HomeAssistantType

from . import async_register_entity
from .coordinator import DeviceCoordinator
from .entity import HaierAbstractEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistantType, entry: ConfigEntry, async_add_entities) -> None:
    def register(coordinator: DeviceCoordinator, spec: str):
        return HaierSensor(coordinator, spec)

    await async_register_entity(hass, entry, async_add_entities, register, 'sensors')


class HaierSensor(HaierAbstractEntity, SensorEntity):

    def __init__(self, coordinator: DeviceCoordinator, spec: dict):
        super().__init__(coordinator, spec)
        if len(spec['value_formatter']) > 0:
            self._attr_device_class = SensorDeviceClass.ENUM
            self._attr_options = list(spec['value_formatter'].values())
        else:
            device_class, unit = self._speculation_device_class()
            if device_class is not None:
                self._attr_device_class = device_class
                self._attr_native_unit_of_measurement = unit

    def _update_value(self):
        formatter = self._spec['value_formatter']
        value = self.coordinator.data[self._spec['key']]
        self._attr_native_value = formatter[str(value)] if str(value) in formatter.keys() else value

    def _speculation_device_class(self):
        if self._spec['unit'] in ['L']:
            return SensorDeviceClass.WATER, self._spec['unit']

        if self._spec['unit'] in ['℃']:
            return SensorDeviceClass.TEMPERATURE, '°C'

        return None, None




