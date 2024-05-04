import logging

from homeassistant.components.select import SelectEntity
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
        Platform.SELECT,
        lambda device, attribute: HaierSelect(device, attribute)
    )


class HaierSelect(HaierAbstractEntity, SelectEntity):

    def __init__(self, device: HaierDevice, attribute: HaierAttribute):
        super().__init__(device, attribute)

        if 'value_comparison_table' not in attribute.ext.keys():
            raise ValueError('value_comparison_table must exist')

    def _update_value(self):
        self._attr_current_option = self._get_value_from_comparison_table(self._attributes_data[self._attribute.key])

    def select_option(self, option: str) -> None:
        self._send_command({
            self._attribute.key: self._get_value_from_comparison_table(option)
        })

    def _get_value_from_comparison_table(self, value):
        value_comparison_table = self._attribute.ext.get('value_comparison_table', {})
        if str(value) not in value_comparison_table:
            _LOGGER.warning('Device [{}] attribute [{}] value [{}] not recognizable'.format(
                self._device.id, self._attribute.key, value
            ))
            return value

        return value_comparison_table.get(str(value))
