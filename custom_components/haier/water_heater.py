"""Support for water heaters."""
import logging

from homeassistant.components.water_heater import (
    WaterHeaterEntity,
    STATE_GAS,
    SUPPORT_AWAY_MODE,
    SUPPORT_TARGET_TEMPERATURE,
    SUPPORT_OPERATION_MODE,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, STATE_OFF, UnitOfTemperature, TEMP_CELSIUS,Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import DeviceInfo

from . import async_register_entity
from .coordinator import DeviceCoordinator
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
        lambda coordinator, device, attribute: HaierWaterHeater(coordinator, device, attribute)
    )


class HaierWaterHeater(HaierAbstractEntity,WaterHeaterEntity):

    def __init__(self, coordinator: DeviceCoordinator, device: HaierDevice, attribute: HaierAttribute):
        super().__init__(coordinator, device, attribute)
        self._attr_temperature_unit = TEMP_CELSIUS
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
        if 'outWaterTemp' in self.coordinator.data:
            self._attr_current_temperature = float(self.coordinator.data['outWaterTemp'])

        self._attr_target_temperature = float(self.coordinator.data['targetTemp'])

        if not try_read_as_bool(self.coordinator.data['onOffStatus']):
            # 关机状态
            self._attr_current_operation  = STATE_OFF
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

    def set_operation_mode(self,operation_mode):
        """Set operation mode"""
        if operation_mode == STATE_GAS:
            power_state = True
        else:
            power_state = False
        self._send_command({
                'onOffStatus': power_state
            })