"""Support for water heaters."""
import logging

from homeassistant.components.water_heater import (
    WaterHeaterEntity,
    STATE_GAS,
    STATE_PERFORMANCE,
    STATE_HEAT_PUMP,
    SUPPORT_AWAY_MODE,
    SUPPORT_TARGET_TEMPERATURE,
    SUPPORT_OPERATION_MODE,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_OFF, TEMP_CELSIUS, Platform
from homeassistant.core import HomeAssistant

from . import async_register_entity
from .core.attribute import HaierAttribute
from .core.device import HaierDevice
from .entity import HaierAbstractEntity
from .helpers import try_read_as_bool

_LOGGER = logging.getLogger(__name__)

SUPPORT_FLAGS = (
        SUPPORT_AWAY_MODE | SUPPORT_TARGET_TEMPERATURE | SUPPORT_OPERATION_MODE
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
        self._attr_temperature_unit = TEMP_CELSIUS
        self._attr_supported_features = SUPPORT_FLAGS
        # 默认的0-70温度范围太宽，homekit不支持
        self._attr_min_temp = 35
        self._attr_max_temp = 65

    @property
    def operation_list(self):
        """List of available operation modes."""
        if 'dualHeaterMode' in self._attributes_data:
            return [STATE_OFF, STATE_PERFORMANCE,STATE_HEAT_PUMP]
        else:
            return [STATE_OFF, STATE_GAS]

    def set_temperature(self, **kwargs) -> None:
        if 'targetTemp' in self._attributes_data:
            self._send_command({
                'targetTemp': kwargs['temperature']
            })
        elif 'targetTemperature' in self._attributes_data:
            self._send_command({
                'targetTemperature': kwargs['temperature']
            })

    def _update_value(self):
        if 'outWaterTemp' in self._attributes_data:
            self._attr_current_temperature = float(self._attributes_data['outWaterTemp'])
        elif 'currentTemperature' in self._attributes_data:
            self._attr_current_temperature = float(self._attributes_data['currentTemperature'])

        if 'targetTemp' in self._attributes_data:
            self._attr_target_temperature = float(self._attributes_data['targetTemp'])
        elif 'targetTemperature' in self._attributes_data:
            self._attr_target_temperature = float(self._attributes_data['targetTemperature'])

        if not try_read_as_bool(self._attributes_data['onOffStatus']):
            # 关机状态
            self._attr_current_operation = STATE_OFF
            self._attr_is_away_mode_on = True
        elif 'dualHeaterMode' in self._attributes_data and try_read_as_bool(self._attributes_data['dualHeaterMode']):
            # 空气能双源速热
            self._attr_current_operation = STATE_PERFORMANCE
            self._attr_is_away_mode_on = False
        elif 'dualHeaterMode' in self._attributes_data and not try_read_as_bool(self._attributes_data['dualHeaterMode']):
            # 空气能节能模式
            self._attr_current_operation = STATE_HEAT_PUMP
            self._attr_is_away_mode_on = False
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
        if 'dualHeaterMode' in self._attributes_data:
            if operation_mode == STATE_HEAT_PUMP:
                self._send_command({
                    'onOffStatus': True,
                    'dualHeaterMode': False
                })
            elif operation_mode == STATE_PERFORMANCE:
                self._send_command({
                    'onOffStatus': True,
                    'dualHeaterMode': True
                })
            else:
                self._send_command({
                    'onOffStatus': False
                })
            
        else:
            if operation_mode == STATE_GAS:
                power_state = True
            else:
                power_state = False
            self._send_command({
                'onOffStatus': power_state
            })
