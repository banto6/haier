import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity, SwitchDeviceClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.typing import HomeAssistantType

from . import async_register_entity
from .coordinator import DeviceCoordinator
from .entity import HaierAbstractEntity

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
        self._attr_is_on = self.coordinator.data[self._spec['key']]

    def turn_on(self, **kwargs: Any) -> None:
        self._send_command({
            self._spec['key']: True
        })

    def turn_off(self, **kwargs: Any) -> None:
        self._send_command({
            self._spec['key']: False
        })

