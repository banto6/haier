import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv

from .const import DOMAIN
from .core.event import EVENT_DEVICE_CONTROL, fire_event

SERVICE_SEND_RAW_COMMAND = 'send_raw_command'

ATTR_DEVICE_ID = 'device_id'
ATTR_ATTRS = 'attrs'


SEND_RAW_COMMAND_SCHEMA = vol.Schema({
    vol.Required(ATTR_DEVICE_ID): cv.string,
    vol.Required(ATTR_ATTRS): cv.match_all,
})


def async_setup_services(hass: HomeAssistant) -> None:
    """注册原始指令服务。"""
    if hass.services.has_service(DOMAIN, SERVICE_SEND_RAW_COMMAND):
        return

    async def handle_send_raw_command(call: ServiceCall) -> None:
        if not hass.data.get(DOMAIN, {}).get('gateway_connected'):
            raise HomeAssistantError('集成未加载或设备网关未连接，指令无法下发')
        fire_event(hass, EVENT_DEVICE_CONTROL, {
            'deviceId': call.data[ATTR_DEVICE_ID],
            'attributes': call.data[ATTR_ATTRS],
        })

    hass.services.async_register(
        DOMAIN, SERVICE_SEND_RAW_COMMAND, handle_send_raw_command, schema=SEND_RAW_COMMAND_SCHEMA
    )


def async_unload_services(hass: HomeAssistant) -> None:
    """注销原始指令服务。"""
    hass.services.async_remove(DOMAIN, SERVICE_SEND_RAW_COMMAND)
