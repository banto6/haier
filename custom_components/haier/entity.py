import logging
from abc import ABC, abstractmethod

from homeassistant.core import Event
from homeassistant.helpers.entity import DeviceInfo, Entity

from . import DOMAIN
from .core.attribute import HaierAttribute
from .core.const import EVENT_DEVICE_DATA_CHANGED, EVENT_WSS_GATEWAY_STATUS_CHANGED, EVENT_DEVICE_CONTROL
from .core.device import HaierDevice

_LOGGER = logging.getLogger(__name__)


class HaierAbstractEntity(Entity, ABC):

    _device: HaierDevice

    _attribute: HaierAttribute

    def __init__(self, device: HaierDevice, attribute: HaierAttribute):
        self._attr_unique_id = '{}.{}_{}'.format(DOMAIN, device.id, attribute.key).lower()
        self.entity_id = self._attr_unique_id
        self._attr_should_poll = False

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device.id.lower())},
            name=device.name,
            manufacturer='海尔',
            model=device.product_name
        )

        self._attr_name = attribute.display_name
        for key, value in attribute.options.items():
            setattr(self, '_attr_' + key, value)

        self._device = device
        self._attribute = attribute
        # 保存当前设备下所有attribute的数据
        self._attributes_data = {}
        # 取消监听回调
        self._cancel_status_listen = None
        self._cancel_data_listen = None

    def _send_command(self, attributes):
        """
        发送控制命令
        :param attributes:
        :return:
        """
        self.hass.bus.fire(EVENT_DEVICE_CONTROL, {
            'deviceId': self._device.id,
            'attributes': attributes
        })

    @abstractmethod
    def _update_value(self):
        pass

    async def async_added_to_hass(self) -> None:
        # 监听状态
        def status_callback(event):
            self._attr_available = event.data['status']
            self.async_write_ha_state()

        self._cancel_status_listen = self.hass.bus.async_listen(EVENT_WSS_GATEWAY_STATUS_CHANGED, status_callback)

        # 监听数据变化事件
        def data_callback(event):
            if event.data['deviceId'] != self._device.id:
                return

            self._attributes_data = event.data['attributes']
            self._update_value()
            self.async_write_ha_state()

        self._cancel_data_listen = self.hass.bus.async_listen(EVENT_DEVICE_DATA_CHANGED, data_callback)

        # 填充快照值
        data_callback(Event('', data={
            'deviceId': self._device.id,
            'attributes': self._device.attribute_snapshot_data
        }))

    async def async_will_remove_from_hass(self) -> None:
        if self._cancel_status_listen:
            self._cancel_data_listen()

        if self._cancel_status_listen:
            self._cancel_data_listen()



