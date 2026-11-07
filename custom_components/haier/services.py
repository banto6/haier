import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv

from .const import DOMAIN
from .core.event import EVENT_DEVICE_CONTROL, fire_event
from .core.runtime import HaierRuntimeData

SERVICE_SEND_RAW_COMMAND = 'send_raw_command'

ATTR_DEVICE_ID = 'device_id'
ATTR_ATTRS = 'attrs'


SEND_RAW_COMMAND_SCHEMA = vol.Schema({
    vol.Required(ATTR_DEVICE_ID): cv.string,
    vol.Required(ATTR_ATTRS): cv.match_all,
})


def _find_runtime(hass: HomeAssistant, device_id: str) -> HaierRuntimeData | None:
    """找到设备所属条目的运行时状态。

    服务是 domain 级的，调用时没有条目上下文，只能按设备归属反查。
    多个条目各自管理不同账号的设备，按设备找才不会把命令发给别的账号。

    :param hass: Home Assistant 实例
    :param device_id: 设备 ID
    :return: 命中的运行时状态，找不到时返回 None
    """
    target = device_id.lower()
    for entry in hass.config_entries.async_entries(DOMAIN):
        runtime: HaierRuntimeData | None = getattr(entry, 'runtime_data', None)
        if runtime is None:
            continue

        if any(device.id.lower() == target for device in runtime.devices):
            return runtime

    return None


def async_setup_services(hass: HomeAssistant) -> None:
    """注册原始指令服务。"""
    if hass.services.has_service(DOMAIN, SERVICE_SEND_RAW_COMMAND):
        return

    async def handle_send_raw_command(call: ServiceCall) -> None:
        device_id = call.data[ATTR_DEVICE_ID]

        runtime = _find_runtime(hass, device_id)
        if runtime is None:
            raise HomeAssistantError('未找到设备 {} 所属的集成条目'.format(device_id))

        if not runtime.gateway.connected:
            raise HomeAssistantError('设备网关未连接，指令无法下发')

        fire_event(hass, EVENT_DEVICE_CONTROL, {
            'entry_id': runtime.entry_id,
            'deviceId': device_id,
            'attributes': call.data[ATTR_ATTRS],
        })

    hass.services.async_register(
        DOMAIN, SERVICE_SEND_RAW_COMMAND, handle_send_raw_command, schema=SEND_RAW_COMMAND_SCHEMA
    )


def async_unload_services(hass: HomeAssistant) -> None:
    """注销原始指令服务。"""
    hass.services.async_remove(DOMAIN, SERVICE_SEND_RAW_COMMAND)
