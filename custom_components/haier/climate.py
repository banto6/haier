import logging

from homeassistant.components.climate import ClimateEntity, ClimateEntityFeature, HVACMode, FAN_MIDDLE, FAN_HIGH, \
    FAN_MEDIUM, FAN_LOW, SWING_OFF, SWING_VERTICAL, SWING_HORIZONTAL, SWING_BOTH, FAN_OFF, FAN_AUTO
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import TEMP_CELSIUS, Platform
from homeassistant.helpers.typing import HomeAssistantType

from . import async_register_entity
from .coordinator import DeviceCoordinator
from .core.attribute import HaierAttribute
from .core.device import HaierDevice
from .entity import HaierAbstractEntity
from .helpers import try_read_as_bool

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistantType, entry: ConfigEntry, async_add_entities) -> None:
    await async_register_entity(
        hass,
        entry,
        async_add_entities,
        Platform.CLIMATE,
        lambda coordinator, device, attribute: HaierClimate(coordinator, device, attribute)
    )


class HaierClimate(HaierAbstractEntity, ClimateEntity):

    def __init__(self, coordinator: DeviceCoordinator, device: HaierDevice, attribute: HaierAttribute):
        super().__init__(coordinator, device, attribute)
        self._attr_temperature_unit = TEMP_CELSIUS
        self._attr_max_temp = 30
        self._attr_min_temp = 16
        self._attr_target_temperature_step = 1
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
        if 'indoorTemperature' in self.coordinator.data:
            self._attr_current_temperature = float(self.coordinator.data['indoorTemperature'])

        if 'indoorHumidity' in self.coordinator.data:
            self._attr_current_humidity = float(self.coordinator.data['indoorHumidity'])

        self._attr_target_temperature = float(self.coordinator.data['targetTemperature'])

        if not try_read_as_bool(self.coordinator.data['onOffStatus']):
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
            }.get(int(self.coordinator.data['operationMode']))

            self._attr_fan_mode = {
                1: FAN_HIGH,
                2: FAN_MEDIUM,
                3: FAN_LOW,
                5: FAN_AUTO
            }.get(int(self.coordinator.data['windSpeed']))

            wind_direction_vertical = int(self.coordinator.data['windDirectionVertical'])
            wind_direction_horizontal = int(self.coordinator.data['windDirectionHorizontal'])
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
        self._send_command({
            'windSpeed': {
                FAN_HIGH: 1,
                FAN_MEDIUM: 2,
                FAN_LOW: 3,
                FAN_AUTO: 5
            }[fan_mode]
        })

    def set_swing_mode(self, swing_mode: str) -> None:
        if swing_mode == SWING_OFF:
            self._send_command({
                'windDirectionVertical': 0,
                'windDirectionHorizontal': 0
            })

        if swing_mode == SWING_HORIZONTAL:
            self._send_command({
                'windDirectionVertical': 0,
                'windDirectionHorizontal': 7
            })

        if swing_mode == SWING_VERTICAL:
            self._send_command({
                'windDirectionVertical': 8,
                'windDirectionHorizontal': 0
            })

        if swing_mode == SWING_BOTH:
            self._send_command({
                'windDirectionVertical': 8,
                'windDirectionHorizontal': 7
            })

    def set_temperature(self, **kwargs) -> None:
        self._send_command({
            'targetTemperature': kwargs['temperature']
        })

