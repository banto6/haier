import time
from typing import List

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from custom_components.haier.const import FILTER_TYPE_EXCLUDE, FILTER_TYPE_INCLUDE


class AccountConfig:
    """
    账户配置
    """

    client_id: str = None

    token: str = None

    refresh_token: str = None

    expires_at: int = None

    default_load_all_entity: bool = None

    def __init__(self, hass: HomeAssistant, config: ConfigEntry):
        self._hass = hass
        self._config = config

        cfg = config.data.get('account', {})
        self.client_id = cfg.get('client_id', '')
        self.token = cfg.get('token', '')
        self.refresh_token = cfg.get('refresh_token', '')
        self.expires_at = cfg.get('expires_at', 0)
        self.default_load_all_entity = cfg.get('default_load_all_entity', True)

    def save(self, mobile: str = None):
        self._hass.config_entries.async_update_entry(
            self._config,
            title='Haier: {}'.format(mobile) if mobile else self._config.title,
            data={
                **self._config.data,
                'account': {
                    'client_id': self.client_id,
                    'token': self.token,
                    'refresh_token': self.refresh_token,
                    'expires_at': self.expires_at,
                    'default_load_all_entity': self.default_load_all_entity
                }
            }
        )


class DeviceFilterConfig:
    """
    设备筛选配置
    """
    _filter_type: str

    _target_devices: List[str]

    def __init__(self, hass: HomeAssistant, config: ConfigEntry):
        self._hass = hass
        self._config = config

        cfg = config.data.get('device_filter', {})
        self._filter_type = cfg.get('filter_type', FILTER_TYPE_EXCLUDE)
        self._target_devices = cfg.get('target_devices', [])

    def set_filter_type(self, filter_type: str):
        if filter_type not in [FILTER_TYPE_EXCLUDE, FILTER_TYPE_INCLUDE]:
            raise ValueError()

        self._filter_type = filter_type

    @property
    def filter_type(self):
        return self._filter_type

    def set_target_devices(self, devices: List[str]):
        if not isinstance(devices, list):
            raise ValueError()

        self._target_devices = devices

    @property
    def target_devices(self):
        return self._target_devices

    def add_device(self, device: str):
        if device not in self._target_devices:
            self._target_devices.append(device)

    def remove_device(self, device: str):
        self._target_devices.remove(device)

    @staticmethod
    def is_skip(hass: HomeAssistant, config: ConfigEntry, device_id: str) -> bool:
        cfg = DeviceFilterConfig(hass, config)
        if cfg.filter_type == FILTER_TYPE_EXCLUDE:
            return device_id in cfg.target_devices
        else:
            return device_id not in cfg.target_devices

    def save(self):
        self._hass.config_entries.async_update_entry(
            self._config,
            data={
                **self._config.data,
                'device_filter': {
                    'filter_type': self._filter_type,
                    'target_devices': self._target_devices
                }
            }
        )


class EntityFilterConfig:
    """
    实体筛选配置
    """
    _cfg: List[dict] = []

    def __init__(self, hass: HomeAssistant, config: ConfigEntry):
        self._hass = hass
        self._config = config
        self._account_cfg = AccountConfig(hass, config)
        self._cfg = config.data.get('entity_filter', [])

    def set_filter_type(self, device_id: str, filter_type: str):
        if filter_type not in [FILTER_TYPE_EXCLUDE, FILTER_TYPE_INCLUDE]:
            raise ValueError()

        for index, item in enumerate(self._cfg):
            if item['device_id'] == device_id:
                self._cfg[index]['filter_type'] = filter_type
                break
        else:
            self._cfg.append(self._generate_entity_filer_item(device_id, filter_type=filter_type))

    def get_filter_type(self, device_id: str) -> str:
        for item in self._cfg:
            if item['device_id'] == device_id:
                return item['filter_type']
        else:
            return FILTER_TYPE_EXCLUDE if self._account_cfg.default_load_all_entity else FILTER_TYPE_INCLUDE

    def set_target_entities(self, device_id: str, entities: List[str]):
        if not isinstance(entities, list):
            raise ValueError()

        for index, item in enumerate(self._cfg):
            if item['device_id'] == device_id:
                self._cfg[index]['target_entities'] = entities
                break
        else:
            self._cfg.append(self._generate_entity_filer_item(device_id, target_entities=entities))

    def get_target_entities(self, device_id: str) -> List[str]:
        for item in self._cfg:
            if item['device_id'] == device_id:
                return item['target_entities']
        else:
            return []

    @staticmethod
    def is_skip(hass: HomeAssistant, config: ConfigEntry, device_id: str, attr: str) -> bool:
        cfg = EntityFilterConfig(hass, config)

        filter_type = cfg.get_filter_type(device_id)
        target_entities = cfg.get_target_entities(device_id)

        if filter_type == FILTER_TYPE_EXCLUDE:
            return attr in target_entities
        else:
            return attr not in target_entities

    def save(self):
        self._hass.config_entries.async_update_entry(
            self._config,
            data={
                **self._config.data,
                'entity_filter': self._cfg,
                # async_update_entry 内部 entry.data != data 无法识别数组内容修改
                # 所以额外添加更新时间用于修复配置无法保存的问题，没有实际用途
                'entity_filter_updated_at': int(time.time())
            }
        )

    @staticmethod
    def _generate_entity_filer_item(device_id: str, filter_type: str = FILTER_TYPE_INCLUDE, entities: List[str] = []):
        return {
            'device_id': device_id,
            'filter_type': filter_type,
            'target_entities': entities
        }
