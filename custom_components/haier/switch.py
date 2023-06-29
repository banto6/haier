import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity, SwitchDeviceClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.typing import HomeAssistantType

from . import async_register_entity
from .coordinator import DeviceCoordinator
from .entity import HaierAbstractEntity
from .helpers import try_read_as_bool

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistantType, entry: ConfigEntry, async_add_entities) -> None:
    def register(coordinator: DeviceCoordinator, spec: str):
        return HaierSwitch(coordinator, spec)

    await async_register_entity(hass, entry, async_add_entities, register, 'switch')


class HaierSwitch(HaierAbstractEntity, SwitchEntity):

    def __init__(self, coordinator: DeviceCoordinator, spec: str):
        super().__init__(coordinator, spec)
        self.__attr_device_class = SwitchDeviceClass.SWITCH

    def _update_value(self):
        try:
            self._attr_is_on = try_read_as_bool(self.coordinator.data[self._spec['key']])
        except ValueError:
            _LOGGER.exception('entity [{}] read value failed'.format(self._attr_unique_id))
            self._attr_available = False

    def turn_on(self, **kwargs: Any) -> None:
        self._send_command({
            self._spec['key']: True
        })

    def turn_off(self, **kwargs: Any) -> None:
        self._send_command({
            self._spec['key']: False
        })

