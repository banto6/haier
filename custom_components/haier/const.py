from homeassistant.const import Platform

DOMAIN = 'haier'

PLATFORMS = [
    Platform.SELECT,
    Platform.NUMBER,
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.SWITCH
]

CONF_ACCOUNT = 'account'
CONF_DEVICE_FILTER = 'device_filter'
CONF_FILTER_TYPE = 'filter_type'
CONF_TARGET_DEVICES = 'target_devices'
