import asyncio
import logging
from abc import ABC
from typing import List

from homeassistant.components.number import NumberEntity
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
        for number in coordinator.numbers:
            if number['key'] not in coordinator.data.keys():
                _LOGGER.warning('{} not found in the data source'.format(number['key']))
                continue

            entities.append(HaierNumber(coordinator, number))

    async_add_entities(entities)


class HaierNumber(CoordinatorEntity, NumberEntity, ABC):

    def __init__(self, coordinator: DeviceCoordinator, number_config: str):
        super().__init__(coordinator, context=coordinator.device_id)
        self._attr_unique_id = '{}_{}'.format(coordinator.device_id, number_config['key']).lower()
        self._attr_name = number_config['key']
        self._attr_device_info = coordinator.device
        self._attr_native_min_value = number_config['minValue']
        self._attr_native_max_value = number_config['maxValue']
        self._attr_native_step = number_config['step']
        self._number_config = number_config
        self._attr_native_value = self.coordinator.data[self._number_config['key']]

    @callback
    def _handle_coordinator_update(self) -> None:
        self._attr_native_value = self.coordinator.data[self._number_config['key']]
        self.async_write_ha_state()

    def set_native_value(self, value: float) -> None:
        async def execute():
            await self.coordinator.client.send_command(
                self.coordinator.device_id,
                {
                    self._number_config['key']: value
                }
            )
            self._attr_native_value = value
            self.async_write_ha_state()

        asyncio.run(execute())
