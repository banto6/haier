import logging
from abc import ABC
from typing import List

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import callback
from homeassistant.helpers.typing import HomeAssistantType
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from . import DeviceCoordinator
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistantType, entry: ConfigEntry, async_add_entities) -> None:
    coordinators: List[DeviceCoordinator] = hass.data[DOMAIN]['coordinators']
    entities = []

    for coordinator in coordinators:
        for sensor in coordinator.sensors:
            if sensor['key'] not in coordinator.data.keys():
                _LOGGER.warning('{} not found in the data source'.format(sensor['key']))
                continue

            entities.append(HaierSensor(coordinator, sensor))

    async_add_entities(entities)


class HaierSensor(CoordinatorEntity, SensorEntity, ABC):

    def __init__(self, coordinator: DeviceCoordinator, sensor: str):
        super().__init__(coordinator, context=coordinator.device_id)
        self._attr_unique_id = '{}_{}'.format(coordinator.device_id, sensor['key']).lower()
        self._attr_name = sensor['key']
        self._attr_device_info = coordinator.device
        self._sensor = sensor
        self._attr_native_value = self.coordinator.data[self._sensor['key']]

    @callback
    def _handle_coordinator_update(self) -> None:
        self._attr_native_value = self.coordinator.data[self._sensor['key']]
        self.async_write_ha_state()
