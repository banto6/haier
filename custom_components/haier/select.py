import asyncio
import logging
from abc import ABC
from typing import List

from homeassistant.components.select import SelectEntity
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
        for select in coordinator.selects:
            if select['key'] not in coordinator.data.keys():
                _LOGGER.warning('{} not found in the data source'.format(select['key']))
                continue

            entities.append(HaierSelect(coordinator, select))

    async_add_entities(entities)


class HaierSelect(CoordinatorEntity, SelectEntity, ABC):

    def __init__(self, coordinator: DeviceCoordinator, select_config: str):
        super().__init__(coordinator, context=coordinator.device_id)
        self._attr_unique_id = '{}_{}'.format(coordinator.device_id, select_config['key']).lower()
        self._attr_name = select_config['key']
        self._attr_device_info = coordinator.device
        self._attr_options = [option['label'] for option in select_config['options']]
        self._select_config = select_config
        self._attr_current_option = self._value_to_option(self.coordinator.data[self._select_config['key']])

    @callback
    def _handle_coordinator_update(self) -> None:
        self._attr_current_option = self._value_to_option(self.coordinator.data[self._select_config['key']])
        self.async_write_ha_state()

    def select_option(self, option: str) -> None:
        async def execute():
            await self.coordinator.client.send_command(
                self.coordinator.device_id,
                {
                    self._select_config['key']: self._option_to_value(option)
                }
            )
            self._attr_current_option = option
            self.async_write_ha_state()

        asyncio.run(execute())

    def _option_to_value(self, option):
        for item in self._select_config['options']:
            if item['label'] == option:
                return item['value']
        else:
            raise ValueError('{} not found'.format(option))

    def _value_to_option(self, value):
        for item in self._select_config['options']:
            if str(item['value']) == str(value):
                return item['label']
        else:
            raise ValueError('{} not found'.format(value))

