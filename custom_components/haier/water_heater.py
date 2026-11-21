"""Support for water heaters."""
import asyncio
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

# HA 2026.11 起 water_heater 使用 native_temperature_* 属性，旧版本仍用 temperature_* 属性
NATIVE_TEMPERATURE = hasattr(WaterHeaterEntity, 'native_current_temperature')


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities) -> None:
    await async_register_entity(
        hass,
        entry,
        async_add_entities,
        Platform.WATER_HEATER,
        lambda device, attribute: (
            HaierElectricWaterHeater(device, attribute)
            if attribute.ext.get('water_heater_type') == 'electric'
            else HaierWaterHeater(device, attribute)
        )
    )


class HaierWaterHeater(HaierAbstractEntity, WaterHeaterEntity):

    def __init__(self, device: HaierDevice, attribute: HaierAttribute):
        super().__init__(device, attribute)
        self._attr_temperature_unit = UnitOfTemperature.CELSIUS
        self._attr_supported_features = SUPPORT_FLAGS

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


class HaierElectricWaterHeater(HaierAbstractEntity, WaterHeaterEntity):
    """储水式电热水器。

    物模型中 targetTemperature 为只读属性，控温实际使用可写的组命令
    scourTargetTemp（“洗浴温度”）；heatingMode（半胆加热/整胆加热）只在
    开机状态下写入才会生效，因此从关机状态切换到加热模式时会先开机，
    待设备真正开机后再下发模式命令。
    """

    def __init__(self, device: HaierDevice, attribute: HaierAttribute):
        super().__init__(device, attribute)

        if NATIVE_TEMPERATURE:
            self._attr_native_temperature_unit = UnitOfTemperature.CELSIUS
        else:
            self._attr_temperature_unit = UnitOfTemperature.CELSIUS

        self._attr_supported_features = (
            WaterHeaterEntityFeature.TARGET_TEMPERATURE
            | WaterHeaterEntityFeature.OPERATION_MODE
            | WaterHeaterEntityFeature.ON_OFF
        )

        ext = attribute.ext
        self._set_temperature_key = ext.get('set_temperature_key', 'scourTargetTemp')
        self._target_temperature_key = ext.get('target_temperature_key', 'targetTemperature')
        self._current_temperature_key = ext.get('current_temperature_key', 'currentTemperature')
        self._on_off_key = ext.get('on_off_key', 'onOffStatus')
        self._heating_mode_key = ext.get('heating_mode_key', 'heatingMode')
        self._heating_mode_value_by_option = ext.get(
            'heating_mode_value_by_option', {'半胆加热': '1', '整胆加热': '2'}
        )
        self._heating_mode_option_by_value = ext.get(
            'heating_mode_option_by_value', {'1': '半胆加热', '2': '整胆加热'}
        )
        self._default_operation = ext.get('default_operation', '整胆加热')

        self._attr_current_operation = STATE_OFF

    @property
    def operation_list(self):
        """List of available operation modes."""
        return [STATE_OFF, *self._heating_mode_value_by_option.keys()]

    def set_temperature(self, **kwargs) -> None:
        """Set new target temperature."""
        temperature = kwargs.get('temperature')
        if temperature is None:
            return

        value = float(temperature)
        # 物模型 dataType 为 Integer，云端接受的属性值为字符串
        if float(self._attribute.options.get('target_temperature_step') or 1) >= 1:
            value = int(round(value))

        self._send_command({
            self._set_temperature_key: str(value)
        })

    def turn_on(self, **kwargs) -> None:
        """Turn the water heater on."""
        self._send_command({
            self._on_off_key: True
        })

    def turn_off(self, **kwargs) -> None:
        """Turn the water heater off."""
        self._send_command({
            self._on_off_key: False
        })

    def set_operation_mode(self, operation_mode: str) -> None:
        """Set new operation mode."""
        if operation_mode == STATE_OFF:
            self._send_command({
                self._on_off_key: False
            })
            return

        mode_value = self._heating_mode_value_by_option.get(operation_mode)
        if mode_value is None:
            raise ValueError('Unsupported operation mode: {}'.format(operation_mode))

        if self._is_power_on():
            self._send_command({
                self._heating_mode_key: mode_value
            })
            return

        # 关机状态下 heatingMode 命令不会生效，需要先开机再下发加热模式
        self._send_command({
            self._on_off_key: True
        })
        self._send_command_later({
            self._heating_mode_key: mode_value
        }, delay=3)

    def _is_power_on(self) -> bool:
        try:
            return try_read_as_bool(self._attributes_data.get(self._on_off_key))
        except ValueError:
            return False

    def _send_command_later(self, attributes: dict, delay: float) -> None:
        """延迟发送控制命令（如开机后再切换加热模式）。"""

        async def send_later():
            await asyncio.sleep(delay)
            self._send_command(attributes)

        # set_operation_mode 在 executor 线程中执行，使用 add_job 调度回事件循环
        self.hass.add_job(send_later)

    def _update_value(self):
        data = self._attributes_data

        current_temperature = data.get(self._current_temperature_key)
        if current_temperature is not None:
            if NATIVE_TEMPERATURE:
                self._attr_native_current_temperature = float(current_temperature)
            else:
                self._attr_current_temperature = float(current_temperature)

        target_temperature = data.get(self._target_temperature_key)
        if target_temperature is not None:
            if NATIVE_TEMPERATURE:
                self._attr_native_target_temperature = float(target_temperature)
            else:
                self._attr_target_temperature = float(target_temperature)

        on_off = data.get(self._on_off_key)
        if on_off is not None and not try_read_as_bool(on_off):
            # 关机状态
            self._attr_current_operation = STATE_OFF
            return

        heating_mode = data.get(self._heating_mode_key)
        if heating_mode is not None:
            self._attr_current_operation = self._heating_mode_option_by_value.get(
                str(heating_mode), self._default_operation
            )
