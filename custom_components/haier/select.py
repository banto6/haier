import logging

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.typing import HomeAssistantType

from . import async_register_entity
from .coordinator import DeviceCoordinator
from .entity import HaierAbstractEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistantType, entry: ConfigEntry, async_add_entities) -> None:
    def register(coordinator: DeviceCoordinator, spec: str):
        return HaierSelect(coordinator, spec)

    await async_register_entity(hass, entry, async_add_entities, register, 'selects')


class HaierSelect(HaierAbstractEntity, SelectEntity):

    def __init__(self, coordinator: DeviceCoordinator, spec: str):
        super().__init__(coordinator, spec)
        self._attr_options = [option['label'] for option in spec['options']]

    def _update_value(self):
        self._attr_current_option = self._value_to_option(self.coordinator.data[self._spec['key']])

    def select_option(self, option: str) -> None:
        self._send_command({
            self._spec['key']: self._option_to_value(option)
        })

    def _option_to_value(self, option):
        for item in self._spec['options']:
            if item['label'] == option:
                return item['value']
        else:
            raise ValueError('{} not found'.format(option))

    def _value_to_option(self, value):
        for item in self._spec['options']:
            if str(item['value']) == str(value):
                return item['label']
        else:
            raise ValueError('{} not found'.format(value))
