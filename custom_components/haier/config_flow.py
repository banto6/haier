import logging
import time
from typing import Any, Dict

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_TOKEN
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.config_validation import multi_select

from .const import DOMAIN, FILTER_TYPE_EXCLUDE, FILTER_TYPE_INCLUDE
from .core.client import HaierClientException, HaierClient
from .core.config import AccountConfig, DeviceFilterConfig, EntityFilterConfig

_LOGGER = logging.getLogger(__name__)

CLIENT_ID = 'client_id'
REFRESH_TOKEN = 'refresh_token'

class HaierConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 2

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        errors: Dict[str, str] = {}
        if user_input is not None:
            try:
                # 根据refresh_token获取token
                client = HaierClient(self.hass, user_input[CLIENT_ID], '')
                token_info = await client.refresh_token(user_input[REFRESH_TOKEN])
                # 获取用户信息
                client = HaierClient(self.hass, user_input[CLIENT_ID], token_info.token)
                user_info = await client.get_user_info()

                return self.async_create_entry(title="Haier - {}".format(user_info['mobile']), data={
                    'account': {
                        'client_id': user_input[CLIENT_ID],
                        'token': token_info.token,
                        'refresh_token': token_info.refresh_token,
                        'expires_at': int(time.time()) + token_info.expires_in,
                        'default_load_all_entity': user_input['default_load_all_entity']
                    }
                })
            except HaierClientException as e:
                _LOGGER.warning(str(e))
                errors['base'] = 'auth_error'

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CLIENT_ID): str,
                    vol.Required(REFRESH_TOKEN): str,
                    vol.Required('default_load_all_entity', default=True): bool,
                }
            ),
            errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> config_entries.OptionsFlow:
        return OptionsFlowHandler(config_entry)


class OptionsFlowHandler(config_entries.OptionsFlow):
    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self.config_entry = config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """
        功能菜单
        :param user_input:
        :return:
        """
        return self.async_show_menu(
            step_id="init",
            menu_options=['account', 'device', 'entity_device_selector']
        )

    async def async_step_account(self,  user_input: dict[str, Any] | None = None) -> FlowResult:
        """
        账号设置
        :param user_input:
        :return:
        """
        errors: Dict[str, str] = {}

        cfg = AccountConfig(self.hass, self.config_entry)

        if user_input is not None:
            try:
                # 根据refresh_token获取token
                client = HaierClient(self.hass, user_input[CLIENT_ID], '')
                token_info = await client.refresh_token(user_input[REFRESH_TOKEN])
                # 获取用户信息
                client = HaierClient(self.hass, user_input[CLIENT_ID], token_info.token)
                user_info = await client.get_user_info()

                cfg.client_id = user_input[CLIENT_ID]
                cfg.token = token_info.token
                cfg.refresh_token = token_info.refresh_token
                cfg.expires_at = int(time.time()) + token_info.expires_in
                cfg.default_load_all_entity = user_input['default_load_all_entity']
                cfg.save(user_info['mobile'])

                await self.hass.config_entries.async_reload(self.config_entry.entry_id)

                return self.async_create_entry(title='', data={})
            except HaierClientException as e:
                _LOGGER.warning(str(e))
                errors['base'] = 'auth_error'

        return self.async_show_form(
            step_id="account",
            data_schema=vol.Schema(
                {
                    vol.Required(CLIENT_ID, default=cfg.client_id): str,
                    vol.Required(REFRESH_TOKEN, default=cfg.refresh_token): str,
                    vol.Required('default_load_all_entity', default=cfg.default_load_all_entity): bool,
                }
            ),
            errors=errors
        )

    async def async_step_device(self,  user_input: dict[str, Any] | None = None) -> FlowResult:
        """
        筛选设备
        :param user_input:
        :return:
        """
        cfg = DeviceFilterConfig(self.hass, self.config_entry)

        if user_input is not None:
            cfg.set_filter_type(user_input['filter_type'])
            cfg.set_target_devices(user_input['target_devices'])
            cfg.save()

            return self.async_create_entry(title='', data={})

        devices = {}
        for item in self.hass.data[DOMAIN]['devices']:
            devices[item.id] = item.name

        return self.async_show_form(
            step_id="device",
            data_schema=vol.Schema(
                {
                    vol.Required('filter_type', default=cfg.filter_type): vol.In({
                        FILTER_TYPE_EXCLUDE: 'Exclude',
                        FILTER_TYPE_INCLUDE: 'Include',
                    }),
                    vol.Optional('target_devices', default=cfg.target_devices): multi_select(devices)
                }
            )
        )

    async def async_step_entity_device_selector(self,  user_input: dict[str, Any] | None = None) -> FlowResult:
        """
        筛选实体（设备选择）
        :param user_input:
        :return:
        """
        if user_input is not None:
            self.hass.data[DOMAIN]['entity_filter_target_device'] = user_input['target_device']
            return await self.async_step_entity_filter()

        devices = {}
        for item in self.hass.data[DOMAIN]['devices']:
            devices[item.id] = item.name

        return self.async_show_form(
            step_id="entity_device_selector",
            data_schema=vol.Schema(
                {
                    vol.Required('target_device'): vol.In(devices)
                }
            )
        )

    async def async_step_entity_filter(self,  user_input: dict[str, Any] | None = None) -> FlowResult:
        """
        筛选实体
        :param user_input:
        :return:
        """
        cfg = EntityFilterConfig(self.hass, self.config_entry)

        if user_input is not None:
            cfg.set_filter_type(user_input['device_id'], user_input['filter_type'])
            cfg.set_target_entities(user_input['device_id'], user_input['target_entities'])
            cfg.save()

            await self.hass.config_entries.async_reload(self.config_entry.entry_id)

            return self.async_create_entry(title='', data={})

        target_device_id = self.hass.data[DOMAIN].pop('entity_filter_target_device', '')
        for device in self.hass.data[DOMAIN]['devices']:
            if device.id == target_device_id:
                target_device = device
                break
        else:
            raise ValueError('Device [{}] not found'.format(target_device_id))

        entities = {}
        for attribute in target_device.attributes:
            entities[attribute.key] = attribute.display_name

        filtered = [item for item in cfg.get_target_entities(target_device_id) if item in entities]

        return self.async_show_form(
            step_id="entity_filter",
            data_schema=vol.Schema(
                {
                    vol.Required('device_id', default=target_device_id): str,
                    vol.Required('filter_type', default=cfg.get_filter_type(target_device_id)): vol.In({
                        FILTER_TYPE_EXCLUDE: 'Exclude',
                        FILTER_TYPE_INCLUDE: 'Include',
                    }),
                    vol.Optional('target_entities', default=filtered): multi_select(
                        entities
                    )
                }
            )
        )

