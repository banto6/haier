import json
import logging
from typing import List

from .attribute import HaierAttribute, V1SpecAttributeParser

_LOGGER = logging.getLogger(__name__)


class HaierDevice:
    _raw_data: dict
    _attributes: List[HaierAttribute]

    def __init__(self, client, raw: dict):
        self._client = client
        self._raw_data = raw
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
        if 'productNameT' not in self._raw_data:
            return ''

        return self._raw_data['productNameT']

    @property
    def wifi_type(self):
        return self._raw_data['wifiType']

    @property
    def attributes(self) -> List[HaierAttribute]:
        return self._attributes

    async def async_init(self):
        # 解析Attribute
        # noinspection PyBroadException
        try:
            parser = V1SpecAttributeParser()
            properties = await self._client.get_digital_model(self.id)
            for item in properties:
                try:
                    attr = parser.parse_attribute(item)
                    if attr:
                        self._attributes.append(attr)
                except:
                    _LOGGER.error("Haier device properties error %s", json.dumps(item))

            iter = parser.parse_global(properties)
            if iter:
                for item in iter:
                    self._attributes.append(item)
        except Exception:
            _LOGGER.exception('获取attributes失败')

    def __str__(self) -> str:
        return json.dumps({
            'id': self.id,
            'name': self.name,
            'type': self.type,
            'product_code': self.product_code,
            'product_name': self.product_name,
            'wifi_type': self.wifi_type
        })
