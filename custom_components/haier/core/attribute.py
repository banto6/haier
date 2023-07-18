from abc import abstractmethod, ABC
from typing import List

from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.components.switch import SwitchDeviceClass
from homeassistant.const import Platform, UnitOfTemperature, PERCENTAGE


class HaierAttribute:

    def __init__(self, key: str, display_name: str, platform: Platform, options: dict = {}, ext: dict = {}):
        self._key = key
        self._display_name = display_name
        self._platform = platform
        self._options = options
        self._ext = ext

    @property
    def key(self) -> str:
        return self._key

    @property
    def display_name(self) -> str:
        return self._display_name

    @property
    def platform(self) -> Platform:
        return self._platform

    @property
    def unit(self) -> str:
        """
        获取数据单位
        :return:
        """
        if '温度' in self.display_name:
            return UnitOfTemperature.CELSIUS

        if '湿度' in self.display_name:
            return PERCENTAGE

        return None

    @property
    def options(self) -> dict:
        return self._options

    @property
    def ext(self) -> dict:
        return self._ext


class HaierAttributeParser(ABC):

    @abstractmethod
    def parse_attribute(self, attribute: dict) -> HaierAttribute:
        pass

    @abstractmethod
    def parse_global(self, attributes: List[dict]):
        pass


class V1SpecAttributeParser(HaierAttributeParser, ABC):

    def parse_attribute(self, attribute: dict) -> HaierAttribute:
        if not attribute['writable'] and attribute['readable']:
            return self._parse_as_sensor(attribute)

        if attribute['writable'] and attribute['type'] in ['int', 'double']:
            return self._parse_as_number(attribute)

        if attribute['writable'] and attribute['type'] in ['enum']:
            return self._parse_as_select(attribute)

        if attribute['writable'] and attribute['type'] in ['bool']:
            return self._parse_as_switch(attribute)

        return None

    def parse_global(self, attributes: List[dict]):
        all_attribute_keys = [attribute['name'] for attribute in attributes]
        if len(list(set(['targetTemperature', 'operationMode', 'windSpeed']) - set(all_attribute_keys))) == 0:
            yield self._parse_as_climate(attributes)

    @staticmethod
    def _parse_as_sensor(attribute):
        if attribute['type'] == 'bool':
            return HaierAttribute(attribute['name'], attribute['description'], Platform.BINARY_SENSOR)

        options = {}
        ext = {}
        if attribute['type'] == 'enum':
            value_comparison_table = {}
            for item in attribute['variants']:
                value_comparison_table[item['stdValue']] = item['description']

            options['device_class'] = SensorDeviceClass.ENUM
            options['options'] = list(value_comparison_table.values())
            ext['value_comparison_table'] = value_comparison_table

        if 'unit' in attribute['variants']:
            if attribute['variants']['unit'] in ['L']:
                options['device_class'] = SensorDeviceClass.WATER

            if attribute['variants']['unit'] in ['℃']:
                options['device_class'] = SensorDeviceClass.TEMPERATURE
                options['unit_of_measurement'] = UnitOfTemperature.CELSIUS

        return HaierAttribute(attribute['name'], attribute['description'], Platform.SENSOR, options, ext)

    @staticmethod
    def _parse_as_number(attribute):
        options = {
            'native_min_value': attribute['variants']['minValue'],
            'native_max_value': attribute['variants']['maxValue'],
            'native_step': attribute['variants']['step']
        }

        return HaierAttribute(attribute['name'], attribute['description'], Platform.NUMBER, options)

    @staticmethod
    def _parse_as_select(attribute):
        value_comparison_table = {}
        for item in attribute['variants']:
            value_comparison_table[str(item['stdValue'])] = item['description']
            value_comparison_table[str(item['description'])] = item['stdValue']

        ext = {
            'value_comparison_table': value_comparison_table
        }

        options = {
            'options': [item['description'] for item in attribute['variants']]
        }

        return HaierAttribute(attribute['name'], attribute['description'], Platform.SELECT, options, ext)

    @staticmethod
    def _parse_as_switch(attribute):
        options = {
            'device_class': SwitchDeviceClass.SWITCH
        }

        return HaierAttribute(attribute['name'], attribute['description'], Platform.SWITCH, options)

    @staticmethod
    def _parse_as_climate(attributes: List[dict]):
        ext = {
            'customize': True,
        }

        return HaierAttribute('climate', 'Climate', Platform.CLIMATE, ext=ext)
