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
CONF_ENTITY_FILTER = 'entity_filter'
CONF_FILTER_TYPE = 'filter_type'
CONF_TARGET_DEVICES = 'target_devices'
CONF_TARGET_ENTITIES = 'target_entities'
CONF_DEVICE_ID = 'device_id'
CONF_DEFAULT_LOAD_ALL_ENTITY = 'default_load_all_entity'
