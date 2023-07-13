import json
import logging
from typing import List

from .attribute import HaierAttribute, V1SpecAttributeParser

_LOGGER = logging.getLogger(__name__)


class HaierDevice:
    _raw_data: dict
    _sw_version: str
    _attributes: List[HaierAttribute]

    def __init__(self, client, raw: dict):
        self._client = client
        self._raw_data = raw
        self._sw_version = None
        self._attributes = []

    @property
    def id(self):
        return self._raw_data['deviceId']

    @property
    def name(self):
        return self._raw_data['deviceName']

    @property
    def type(self):
        return self._raw_data['deviceType']

    @property
    def product_code(self):
        return self._raw_data['productCodeT']

    @property
    def product_name(self):
        return self._raw_data['productNameT']

    @property
    def wifi_type(self):
        return self._raw_data['wifiType']

    @property
    def is_virtual(self):
        return 'virtual' in self._raw_data and self._raw_data['virtual']

    @property
    def sw_version(self):
        return self._sw_version

    @property
    def attributes(self) -> List[HaierAttribute]:
        return self._attributes

    async def async_init(self):
        # 获取sw_version
        if self.is_virtual:
            self._sw_version = 'N/A'
        else:
            self._sw_version = (await self._client.get_net_quality_by_device(self.id))['hardwareVers']

        # 解析Attribute
        # noinspection PyBroadException
        try:
            parser = V1SpecAttributeParser()
            properties = (await self._client.get_hardware_config(self.wifi_type))['Property']
            for item in properties:
                self._attributes.append(parser.parse_attribute(item))

            iter = parser.parse_global(properties)
            if iter:
                for item in iter:
                    self._attributes.append(item)
        except Exception:
            _LOGGER.exception('获取attributes失败')

    async def write_attributes(self, values):
        await self._client.send_command(self.id, values)

    async def read_attributes(self):
        return await self._client.get_last_report_status_by_device(self.id)

    def __str__(self) -> str:
        return json.dumps({
            'id': self.id,
            'name': self.name,
            'type': self.type,
            'product_code': self.product_code,
            'product_name': self.product_name,
            'wifi_type': self.wifi_type
        })
