"""Support for water heaters."""
import logging

from homeassistant.components.water_heater import (
    WaterHeaterEntity,
    STATE_GAS,
    WaterHeaterEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_OFF, UnitOfTemperature, Platform
from homeassistant.core import HomeAssistant

from . import async_register_entity
from .core.attribute import HaierAttribute
from .core.device import HaierDevice
from .entity import HaierAbstractEntity
from .helpers import try_read_as_bool

_LOGGER = logging.getLogger(__name__)

SUPPORT_FLAGS = (
    WaterHeaterEntityFeature.AWAY_MODE | WaterHeaterEntityFeature.TARGET_TEMPERATURE | WaterHeaterEntityFeature.OPERATION_MODE
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities) -> None:
    await async_register_entity(
        hass,
        entry,
        async_add_entities,
        Platform.WATER_HEATER,
        lambda device, attribute: HaierWaterHeater(device, attribute)
    )


class HaierWaterHeater(HaierAbstractEntity, WaterHeaterEntity):

    def __init__(self, device: HaierDevice, attribute: HaierAttribute):
        super().__init__(device, attribute)
        self._attr_temperature_unit = UnitOfTemperature.CELSIUS
        self._attr_supported_features = SUPPORT_FLAGS
        # 默认的0-70温度范围太宽，homekit不支持
        self._attr_min_temp = 35
        self._attr_max_temp = 50

    @property
    def operation_list(self):
        """List of available operation modes."""
        return [STATE_OFF, STATE_GAS]

    def set_temperature(self, **kwargs) -> None:
        self._send_command({
            'targetTemp': kwargs['temperature']
        })

    def _update_value(self):
        if 'outWaterTemp' in self._attributes_data:
            self._attr_current_temperature = float(self._attributes_data['outWaterTemp'])

        self._attr_target_temperature = float(self._attributes_data['targetTemp'])

        if not try_read_as_bool(self._attributes_data['onOffStatus']):
            # 关机状态
            self._attr_current_operation = STATE_OFF
            self._attr_is_away_mode_on = True
        else:
            # 开机状态
            self._attr_current_operation = STATE_GAS
            self._attr_is_away_mode_on = False

    def turn_away_mode_on(self):
        """Turn away mode on."""
        self._send_command({
            'onOffStatus': False
        })

    def turn_away_mode_off(self):
        """Turn away mode off."""
        self._send_command({
            'onOffStatus': True
        })

    def set_operation_mode(self, operation_mode):
        """Set operation mode"""
        if operation_mode == STATE_GAS:
            power_state = True
        else:
            power_state = False
        self._send_command({
            'onOffStatus': power_state
        })
