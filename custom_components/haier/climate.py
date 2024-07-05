import logging

from homeassistant.components.climate import ClimateEntity, ClimateEntityFeature, HVACMode, FAN_HIGH, \
    FAN_MEDIUM, FAN_LOW, SWING_OFF, SWING_VERTICAL, SWING_HORIZONTAL, SWING_BOTH, FAN_OFF, FAN_AUTO
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature, Platform
from homeassistant.core import HomeAssistant

from . import async_register_entity
from .core.attribute import HaierAttribute
from .core.device import HaierDevice
from .entity import HaierAbstractEntity
from .helpers import try_read_as_bool

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities) -> None:
    await async_register_entity(
        hass,
        entry,
        async_add_entities,
        Platform.CLIMATE,
        lambda device, attribute: HaierClimate(device, attribute)
    )


class HaierClimate(HaierAbstractEntity, ClimateEntity):

    def __init__(self, device: HaierDevice, attribute: HaierAttribute):
        super().__init__(device, attribute)
        self._attr_temperature_unit = UnitOfTemperature.CELSIUS
        self._attr_hvac_modes = [
            HVACMode.OFF,
            HVACMode.AUTO,
            HVACMode.COOL,
            HVACMode.HEAT,
            HVACMode.DRY,
            HVACMode.FAN_ONLY
        ]

        self._attr_fan_modes = [
            FAN_AUTO,
            FAN_LOW,
            FAN_MEDIUM,
            FAN_HIGH
        ]

        self._attr_swing_modes = [
            SWING_OFF,
            SWING_VERTICAL,
            SWING_HORIZONTAL,
            SWING_BOTH
        ]

        self._attr_supported_features = ClimateEntityFeature.TARGET_TEMPERATURE \
                                        | ClimateEntityFeature.FAN_MODE \
                                        | ClimateEntityFeature.SWING_MODE

    def _update_value(self):
        if 'indoorTemperature' in self._attributes_data:
            self._attr_current_temperature = float(self._attributes_data['indoorTemperature'])

        if 'indoorHumidity' in self._attributes_data and float(self._attributes_data['indoorHumidity']) != 0:
            self._attr_current_humidity = float(self._attributes_data['indoorHumidity'])

        self._attr_target_temperature = float(self._attributes_data['targetTemperature'])

        if not try_read_as_bool(self._attributes_data['onOffStatus']):
            # 关机状态
            self._attr_hvac_mode = HVACMode.OFF
            self._attr_fan_mode = FAN_OFF
            self._attr_swing_mode = SWING_OFF
        else:
            # 开机状态
            self._attr_hvac_mode = {
                0: HVACMode.AUTO,
                1: HVACMode.COOL,
                2: HVACMode.DRY,
                4: HVACMode.HEAT,
                6: HVACMode.FAN_ONLY
            }.get(int(self._attributes_data['operationMode']))

            self._attr_fan_mode = {
                1: FAN_HIGH,
                2: FAN_MEDIUM,
                3: FAN_LOW,
                5: FAN_AUTO
            }.get(int(self._get_wind_speed()))

            wind_direction_vertical = int(self._get_wind_direction_vertical())
            wind_direction_horizontal = int(self._get_wind_direction_horizontal())
            if wind_direction_horizontal == 0 and wind_direction_vertical == 0:
                self._attr_swing_mode = SWING_OFF
            else:
                if wind_direction_horizontal != 0 and wind_direction_vertical != 0:
                    self._attr_swing_mode = SWING_BOTH
                else:
                    if wind_direction_horizontal != 0:
                        self._attr_swing_mode = SWING_HORIZONTAL

                    if wind_direction_vertical != 0:
                        self._attr_swing_mode = SWING_VERTICAL

    def set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        # 关机
        if hvac_mode == HVACMode.OFF:
            self._send_command({
                'onOffStatus': False
            })
            return

        # 关机状态则先开机
        if not try_read_as_bool(self._attributes_data['onOffStatus']):
            self._send_command({
                'onOffStatus': True
            })

        self._send_command({
            'operationMode': {
                HVACMode.AUTO: 0,
                HVACMode.COOL: 1,
                HVACMode.DRY: 2,
                HVACMode.HEAT: 4,
                HVACMode.FAN_ONLY: 6
            }[hvac_mode]
        })

    def set_fan_mode(self, fan_mode: str) -> None:
        value = {
            FAN_HIGH: 1,
            FAN_MEDIUM: 2,
            FAN_LOW: 3,
            FAN_AUTO: 5
        }[fan_mode]

        if self._attribute.ext['exist_multiple_vents']:
            self._send_command({
                'windSpeedL': value,
                'windSpeedR': value
            })
        else:
            self._send_command({
                'windSpeed': value
            })

    def set_swing_mode(self, swing_mode: str) -> None:
        v_h_values = [0, 0]
        if swing_mode == SWING_OFF:
            v_h_values = [0, 0]

        if swing_mode == SWING_HORIZONTAL:
            v_h_values = [0, 7]

        if swing_mode == SWING_VERTICAL:
            v_h_values = [8, 0]

        if swing_mode == SWING_BOTH:
            v_h_values = [8, 7]

        if self._attribute.ext['exist_multiple_vents']:
            self._send_command({
                'windDirectionVerticalL': v_h_values[0],
                'windDirectionVerticalR': v_h_values[0],
                'windDirectionHorizontalL': v_h_values[1],
                'windDirectionHorizontalR': v_h_values[1]
            })
        else:
            self._send_command({
                'windDirectionVertical': v_h_values[0],
                'windDirectionHorizontal': v_h_values[1]
            })

    def set_temperature(self, **kwargs) -> None:
        self._send_command({
            'targetTemperature': kwargs['temperature']
        })

    def _get_wind_speed(self) -> str:
        if self._attribute.ext['exist_multiple_vents']:
            return self._attributes_data['windSpeedL']

        return self._attributes_data['windSpeed']

    def _get_wind_direction_vertical(self) -> str:
        if self._attribute.ext['exist_multiple_vents']:
            return self._attributes_data.get('windDirectionVerticalL', '0')
        return self._attributes_data.get('windDirectionVertical', '0')

    def _get_wind_direction_horizontal(self) -> str:
        if self._attribute.ext['exist_multiple_vents']:
            return self._attributes_data.get('windDirectionHorizontalL', '0')
        return self._attributes_data.get('windDirectionHorizontal', '0')
