import glob
import json
import logging
import os
from abc import ABC
from datetime import datetime
from typing import List

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntry
from homeassistant.helpers.storage import Store

from .const import DOMAIN, SUPPORTED_PLATFORMS, FILTER_TYPE_EXCLUDE, FILTER_TYPE_INCLUDE
from .coordinator import DeviceCoordinator
from .core.attribute import HaierAttribute
from .core.client import HaierClient, TokenHolder
from .core.config import AccountConfig, DeviceFilterConfig, EntityFilterConfig
from .core.device import HaierDevice

_LOGGER = logging.getLogger(__name__)


class HassTokenHolder(TokenHolder, ABC):

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry):
        account_cfg = AccountConfig(hass, entry)
        self._store = Store(hass, 1, 'haier/{}.token'.format(account_cfg.username))

    async def async_set(self, token: str, created_at: datetime):
        await self._store.async_save({
            'token': token,
            'created_at': datetime.timestamp(created_at)
        })
        _LOGGER.debug('token已成功缓存到HomeAssistant中')

    # noinspection PyBroadException
    async def async_get(self) -> (str, datetime):
        try:
            data = await self._store.async_load()
            if not data:
                return None, None

            _LOGGER.debug('已从HomeAssistant加载到缓存的token')

            return data['token'], datetime.fromtimestamp(data['created_at'])
        except Exception:
            await self._store.async_remove()
            _LOGGER.warning('从HomeAssistant中加载token发生异常')
            return None, None


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    hass.data.setdefault(DOMAIN, {
        'coordinators': {},
        'devices': []
    })

    account_cfg = AccountConfig(hass, entry)
    client = HaierClient(account_cfg.username, account_cfg.password, HassTokenHolder(hass, entry))

    devices = await get_available_devices(client)
    hass.data[DOMAIN]['devices'] = devices
    _LOGGER.debug('共获取到{}个设备'.format(len(devices)))

    for platform in SUPPORTED_PLATFORMS:
        hass.async_create_task(
            hass.config_entries.async_forward_entry_setup(entry, platform)
        )

    entry.async_on_unload(entry.add_update_listener(entry_update_listener))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    for platform in SUPPORTED_PLATFORMS:
        if not await hass.config_entries.async_forward_entry_unload(entry, platform):
            return False

    del hass.data[DOMAIN]

    return True


async def entry_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    _LOGGER.debug('reload.....')
    await hass.config_entries.async_reload(entry.entry_id)


async def async_migrate_entry(hass, config_entry: ConfigEntry):
    _LOGGER.info("Migrating from version %s", config_entry.version)

    if config_entry.version == 1:
        config_entry.version = 2
        hass.config_entries.async_update_entry(config_entry, data={
            'account': dict(config_entry.data)
        })

    _LOGGER.info("Migration to version %s successful", config_entry.version)

    return True


async def async_remove_config_entry_device(hass: HomeAssistant, config: ConfigEntry, device: DeviceEntry) -> bool:
    device_id = list(device.identifiers)[0][1]

    _LOGGER.info('Device [{}] removing...'.format(device_id))

    for device in hass.data[DOMAIN]['devices']:
        if device.id.lower() == device_id:
            target_device = device
            break
    else:
        _LOGGER.error('Device [{}] not found'.format(device_id))
        return False

    cfg = DeviceFilterConfig(hass, config)
    if cfg.filter_type == FILTER_TYPE_EXCLUDE:
        cfg.add_device(target_device.id)
    else:
        cfg.remove_device(target_device.id)

    cfg.save()

    _LOGGER.info('Device [{}] removed'.format(device_id))

    return True


async def get_available_devices(client: HaierClient) -> List[HaierDevice]:
    # 从账号中获取所有设备
    devices = await client.get_devices() + await get_virtual_devices(client)
    # 过滤掉未能获取到attribute的设备
    available_devices = []
    for device in devices:
        attributes = device.attributes
        if len(attributes) != 0:
            available_devices.append(device)
        else:
            _LOGGER.error('Device [{}] 未获取到可用attribute'.format(device.id))

    return available_devices


async def get_virtual_devices(client: HaierClient) -> List[HaierDevice]:
    target_folder = os.path.dirname(__file__) + '/virtual_devices'
    if not os.path.exists(target_folder):
        return []

    devices = []
    for file in glob.glob(target_folder + '/*.json'):
        with open(file, 'r') as fp:
            device = json.load(fp)
            device['virtual'] = True
            device = HaierDevice(client, device)
            await device.async_init()
            devices.append(device)

    return devices


async def async_register_entity(hass: HomeAssistant, entry: ConfigEntry, async_add_entities, platform, setup) -> None:
    entities = []
    for device in hass.data[DOMAIN]['devices']:
        if DeviceFilterConfig.is_skip(hass, entry, device.id):
            continue

        # 初始化coordinator
        if device.id not in hass.data[DOMAIN]['coordinators']:
            coordinator = DeviceCoordinator(hass, device)
            await coordinator.async_config_entry_first_refresh()
            hass.data[DOMAIN]['coordinators'][device.id] = coordinator

        coordinator = hass.data[DOMAIN]['coordinators'][device.id]

        for attribute in device.attributes:
            if attribute.platform != platform:
                continue

            if EntityFilterConfig.is_skip(hass, entry, device.id, attribute.key):
                continue

            if attribute.key not in coordinator.data and 'customize' not in attribute.ext:
                _LOGGER.warning(
                    'Device {} attribute {} not found in the coordinator'.format(
                        device.id,
                        attribute.key
                    )
                )
                continue

            entities.append(setup(coordinator, device, attribute))

    async_add_entities(entities)
