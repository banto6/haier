import logging
from typing import Any

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from . import async_register_entity
from .core.attribute import HaierAttribute
from .core.device import HaierDevice
from .entity import HaierAbstractEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities) -> None:
    await async_register_entity(
        hass,
        entry,
        async_add_entities,
        Platform.BUTTON,
        lambda device, attribute: HaierButton(device, attribute)
    )


class HaierButton(HaierAbstractEntity, ButtonEntity):

    def __init__(self, device: HaierDevice, attribute: HaierAttribute):
        super().__init__(device, attribute)

    def _update_value(self):
        # A button has no persistent value.  The base entity still uses each
        # incoming snapshot to mark the command available.
        return None

    def press(self, **kwargs: Any) -> None:
        self._send_command({
            self._attribute.key: self._attribute.ext['command_value']
        })