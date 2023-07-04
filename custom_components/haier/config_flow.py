import json
import logging
from typing import Any, Dict

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_USERNAME, CONF_PASSWORD
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.config_validation import multi_select

from .const import DOMAIN
from .haier import HaierClient, HaierClientException

_LOGGER = logging.getLogger(__name__)


class HaierConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

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

                return self.async_create_entry(title="Haier - {}".format(user_input[CONF_USERNAME]), data=user_input)
            except HaierClientException as e:
                _LOGGER.warning(str(e))
                errors['base'] = 'auth_error'

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_USERNAME): str,
                    vol.Required(CONF_PASSWORD): str,
                }
            ),
            errors=errors
        )

    # @staticmethod
    # @callback
    # def async_get_options_flow(
    #         config_entry: config_entries.ConfigEntry,
    # ) -> config_entries.OptionsFlow:
    #     """Create the options flow."""
    #     return OptionsFlowHandler(config_entry)


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
                    data=user_input
                )

                await self.hass.config_entries.async_reload(self.config_entry.entry_id)

                return self.async_create_entry(title='', data={})
            except HaierClientException as e:
                _LOGGER.warning(str(e))
                errors['base'] = 'auth_error'

        return self.async_show_form(
            step_id="account",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_USERNAME, default=self.config_entry.data[CONF_USERNAME]): str,
                    vol.Required(CONF_PASSWORD, default=self.config_entry.data[CONF_PASSWORD]): str,
                }
            ),
            errors=errors
        )

    async def async_step_device(self,  user_input: dict[str, Any] | None = None) -> FlowResult:
        if user_input is not None:
            _LOGGER.info(json.dumps(user_input))
            return self.async_create_entry(title='device_filter', data=user_input)

        d = {}
        for item in self.hass.data[DOMAIN]['devices']:
            d[item.id] = item.name

        return self.async_show_form(
            step_id="device",
            data_schema=vol.Schema(
                {
                    vol.Required('filter_method', default='exclude'): vol.In({
                        'exclude': 'Exclude',
                        'include': 'Include',
                    }),
                    vol.Optional('devices', default=[]): multi_select(d)
                }
            )
        )

    async def async_step_entity_device_selector(self,  user_input: dict[str, Any] | None = None) -> FlowResult:
        if user_input is not None:
            self.hass.data[DOMAIN]['prev_input'] = user_input
            return await self.async_step_entity_filter()

        d = {}
        for item in self.hass.data[DOMAIN]['devices']:
            d[item.id] = item.name

        return self.async_show_form(
            step_id="entity_device_selector",
            data_schema=vol.Schema(
                {
                    vol.Required('target_device'): vol.In(d)
                }
            )
        )

    async def async_step_entity_filter(self,  user_input: dict[str, Any] | None = None) -> FlowResult:
        if user_input is not None:
            _LOGGER.info(json.dumps(user_input))
            return self.async_create_entry(title='entity_filter', data=user_input)

        prev_input = self.hass.data[DOMAIN].get('prev_input', {})

        d = {}
        for item in self.hass.data[DOMAIN]['devices']:
            d[item.id] = item.name

        return self.async_show_form(
            step_id="entity_filter",
            data_schema=vol.Schema(
                {
                    vol.Required('entity_filter_method', default='include'): vol.In({
                        'exclude': 'Exclude',
                        'include': 'Include',
                    }),
                    vol.Optional('entities', default=[]): multi_select(d)
                }
            )
        )

