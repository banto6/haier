import logging
import time
from typing import Any, Dict

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_USERNAME, CONF_PASSWORD
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.config_validation import multi_select

from .const import DOMAIN, CONF_ACCOUNT, CONF_DEVICE_FILTER, CONF_FILTER_TYPE, CONF_TARGET_DEVICES, \
    CONF_TARGET_ENTITIES, CONF_ENTITY_FILTER, CONF_DEVICE_ID, CONF_DEFAULT_LOAD_ALL_ENTITY
from .haier import HaierClient, HaierClientException

_LOGGER = logging.getLogger(__name__)


class HaierConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 2

    async def async_step_user(
            self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle a flow initiated by the user."""
        errors: Dict[str, str] = {}

        if user_input is not None:
            try:
                # 校验账号密码是否正确
                client = HaierClient(user_input[CONF_USERNAME], user_input[CONF_PASSWORD])
                await client.try_login()

                return self.async_create_entry(title="Haier - {}".format(user_input[CONF_USERNAME]), data={
                    CONF_ACCOUNT: user_input
                })
            except HaierClientException as e:
                _LOGGER.warning(str(e))
                errors['base'] = 'auth_error'

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_USERNAME): str,
                    vol.Required(CONF_PASSWORD): str,
                    vol.Required(CONF_DEFAULT_LOAD_ALL_ENTITY, default=True): bool,
                }
            ),
            errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(
            config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Create the options flow."""
        return OptionsFlowHandler(config_entry)


class OptionsFlowHandler(config_entries.OptionsFlow):
    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self.config_entry = config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        return self.async_show_menu(
            step_id="init",
            menu_options=['account', 'device', 'entity_device_selector']
        )

    async def async_step_account(self,  user_input: dict[str, Any] | None = None) -> FlowResult:
        errors: Dict[str, str] = {}

        if user_input is not None:
            # 校验账号密码是否正确
            client = HaierClient(user_input[CONF_USERNAME], user_input[CONF_PASSWORD])
            try:
                await client.try_login()

                self.hass.config_entries.async_update_entry(
                    self.config_entry,
                    title='Haier - {}'.format(user_input[CONF_USERNAME]),
                    data={
                        **self.config_entry.data,
                        CONF_ACCOUNT: user_input
                    }
                )

                return self.async_create_entry(title='', data={})
            except HaierClientException as e:
                _LOGGER.warning(str(e))
                errors['base'] = 'auth_error'

        cfg = self.config_entry.data.get(CONF_ACCOUNT, {})
        return self.async_show_form(
            step_id="account",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_USERNAME, default=cfg.get(CONF_USERNAME, '')): str,
                    vol.Required(CONF_PASSWORD, default=cfg.get(CONF_PASSWORD, '')): str,
                    vol.Required(CONF_DEFAULT_LOAD_ALL_ENTITY, default=cfg.get(CONF_DEFAULT_LOAD_ALL_ENTITY, False)): bool,
                }
            ),
            errors=errors
        )

    async def async_step_device(self,  user_input: dict[str, Any] | None = None) -> FlowResult:
        if user_input is not None:
            self.hass.config_entries.async_update_entry(
                self.config_entry,
                data={
                    **self.config_entry.data,
                    CONF_DEVICE_FILTER: user_input
                },
            )

            return self.async_create_entry(title='', data={})

        devices = {}
        for item in self.hass.data[DOMAIN]['devices']:
            devices[item.id] = item.name

        cfg = self.config_entry.data.get(CONF_DEVICE_FILTER, {})
        return self.async_show_form(
            step_id="device",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_FILTER_TYPE, default=cfg.get(CONF_FILTER_TYPE, 'exclude')): vol.In({
                        'exclude': 'Exclude',
                        'include': 'Include',
                    }),
                    vol.Optional(CONF_TARGET_DEVICES, default=cfg.get(CONF_TARGET_DEVICES, [])): multi_select(devices)
                }
            )
        )

    async def async_step_entity_device_selector(self,  user_input: dict[str, Any] | None = None) -> FlowResult:
        if user_input is not None:
            device_id, wifi_type = user_input['target_device'].split('#')
            self.hass.data[DOMAIN]['entity_filter_target_device'] = {
                'device_id': device_id,
                'wifi_type': wifi_type
            }
            return await self.async_step_entity_filter()

        devices = {}
        for item in self.hass.data[DOMAIN]['devices']:
            devices[item.id + '#' + item.wifi_type] = item.name

        return self.async_show_form(
            step_id="entity_device_selector",
            data_schema=vol.Schema(
                {
                    vol.Required('target_device'): vol.In(devices)
                }
            )
        )

    async def async_step_entity_filter(self,  user_input: dict[str, Any] | None = None) -> FlowResult:
        if user_input is not None:
            values = self.config_entry.data.get(CONF_ENTITY_FILTER, [])
            for index, value in enumerate(values):
                if value[CONF_DEVICE_ID] == user_input[CONF_DEVICE_ID]:
                    values[index] = user_input
                    break
            else:
                values.append(user_input)

            self.hass.config_entries.async_update_entry(
                self.config_entry,
                data={
                    **self.config_entry.data,
                    CONF_ENTITY_FILTER: values,
                    # async_update_entry 内部 entry.data != data 无法识别数组内容修改
                    # 所以额外添加更新时间用于修复配置无法保存的问题，没有实际用途
                    'entity_filter_updated_at': int(time.time())
                }
            )

            return self.async_create_entry(title='', data={})

        target_device = self.hass.data[DOMAIN].pop('entity_filter_target_device', '')

        client: HaierClient = self.hass.data[DOMAIN]['client']
        spec_resp = await client.get_hardware_config(target_device['wifi_type'])

        entities = {}
        for spec in spec_resp['Property']:
            entities[spec['name']] = spec['description']

        cfg = {}
        for item in self.config_entry.data.get(CONF_ENTITY_FILTER, []):
            if item[CONF_DEVICE_ID] == target_device['device_id']:
                cfg = item
                break

        return self.async_show_form(
            step_id="entity_filter",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_DEVICE_ID, default=target_device['device_id']): str,
                    vol.Required(CONF_FILTER_TYPE, default=cfg.get(CONF_FILTER_TYPE, 'include')): vol.In({
                        'exclude': 'Exclude',
                        'include': 'Include',
                    }),
                    vol.Optional(CONF_TARGET_ENTITIES, default=cfg.get(CONF_TARGET_ENTITIES, [])): multi_select(entities)
                }
            )
        )

