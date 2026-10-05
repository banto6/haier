import logging
from abc import ABC, abstractmethod

from homeassistant.helpers.entity import DeviceInfo, Entity

from . import DOMAIN
from .core.attribute import HaierAttribute
from .core.device import HaierDevice
from .core.event import EVENT_DEVICE_DATA_CHANGED, EVENT_DEVICE_CONTROL, \
    EVENT_DEVICE_ONLINE_CHANGED, EVENT_GATEWAY_DISCONNECTED
from .core.event import listen_event, fire_event

_LOGGER = logging.getLogger(__name__)


class HaierAbstractEntity(Entity, ABC):

    _device: HaierDevice

    _attribute: HaierAttribute

    def __init__(self, device: HaierDevice, attribute: HaierAttribute):
        self._attr_unique_id = '{}.{}_{}'.format(DOMAIN, device.id, attribute.key).lower()
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
        # 默认为不可用状态
        self._attr_available = False
        # 保存当前设备下所有attribute的数据
        self._attributes_data = {}

    def _send_command(self, attributes):
        """
        发送控制命令
        :param attributes:
        :return:
        """
        fire_event(self.hass, EVENT_DEVICE_CONTROL, {
            'deviceId': self._device.id,
            'attributes': attributes
        })

    @abstractmethod
    def _update_value(self):
        pass

    async def async_added_to_hass(self) -> None:
        # 监听网关状态
        def gateway_disconnected_callback(event):
            self._attr_available = False
            self.schedule_update_ha_state()

        self.async_on_remove(listen_event(self.hass, EVENT_GATEWAY_DISCONNECTED, gateway_disconnected_callback))

        # 监听数据变化事件
        def data_callback(event):
            if event.data['deviceId'] != self._device.id:
                return

            self._attr_available = True
            self._attributes_data = event.data['attributes']
            try:
                self._update_value()
            except KeyError as e:
                # 云端下发的快照并不总是包含该设备的全部属性，缺少本实体所需的
                # 属性时保留上一次的值，等待下一次包含该属性的推送。
                _LOGGER.debug(
                    'entity [%s] attribute %s missing in this snapshot, keep previous value',
                    self._attr_unique_id, e
                )
                return
            self.schedule_update_ha_state()

        self.async_on_remove(listen_event(self.hass, EVENT_DEVICE_DATA_CHANGED, data_callback))

        # 监听设备在线状态
        def device_online_callback(event):
            if event.data['deviceId'] != self._device.id:
                return

            # 配置为忽略设备在线/离线状态时，可用性完全由数据和网关连接驱动，
            # 不再随设备上线/离线变化，从而在设备离线时保留最后一次的状态
            if self.hass.data[DOMAIN]['ignore_device_offline']:
                return

            self._attr_available = event.data['online']
            self.schedule_update_ha_state()

        self.async_on_remove(listen_event(self.hass, EVENT_DEVICE_ONLINE_CHANGED, device_online_callback))
