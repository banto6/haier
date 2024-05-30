from typing import Callable, Coroutine, Any

from homeassistant.core import HomeAssistant, CALLBACK_TYPE, Event

from custom_components.haier import DOMAIN

EVENT_DEVICE_CONTROL = 'device_control'
EVENT_DEVICE_DATA_CHANGED = 'device_data_changed'
EVENT_GATEWAY_STATUS_CHANGED = 'gateway_status_changed'


def wrap_event(name: str) -> str:
    return '{}_{}'.format(DOMAIN, name)


def fire_event(hass: HomeAssistant, event: str, data: dict) -> None:
    hass.bus.fire(wrap_event(event), data)


def listen_event(
        hass: HomeAssistant,
        event: str,
        callback: Callable[[Event], Coroutine[Any, Any, None] | None]
) -> CALLBACK_TYPE:
    return hass.bus.async_listen(wrap_event(event), callback)
