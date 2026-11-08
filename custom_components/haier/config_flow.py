import logging
import time
from dataclasses import dataclass
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry, ConfigFlowResult
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import AbortFlow
from homeassistant.helpers import config_entry_oauth2_flow
from homeassistant.helpers.config_entry_oauth2_flow import (
    async_register_implementation,
)
from homeassistant.helpers.config_validation import multi_select

from .const import (
    CONFIG_ENTRY_VERSION,
    DEFAULT_LANGUAGE,
    DEFAULT_REGION,
    DOMAIN,
    FILTER_TYPE_EXCLUDE,
    FILTER_TYPE_INCLUDE,
    OAUTH2_CALLBACK_URL,
)
from .core.client import HaierClientException, HaierClient, APP_SOURCE_APP, APP_SOURCE_OAUTH, APP_SOURCE_WXAPP, DEFAULT_APP_SOURCE
from .core.config import (
    AccountConfig,
    DeviceFilterConfig,
    EntityFilterConfig,
    PreferencesConfig,
)
from .haier import (
    async_get_account_info,
    generate_ag_client_id,
)
from .haier.oauth2 import (
    HaierOAuth2Implementation,
    get_redirect_uri,
    is_registered_callback,
    supports_oauth2_login,
)

_LOGGER = logging.getLogger(__name__)

CLIENT_ID = 'client_id'
REFRESH_TOKEN = 'refresh_token'
APP_SOURCE = 'app_source'

APP_SOURCE_OPTIONS = {
    APP_SOURCE_WXAPP: '微信小程序',
    APP_SOURCE_APP: 'App',
}


@dataclass(frozen=True)
class AuthenticationResult:
    """认证成功结果。"""

    account: dict[str, Any]
    mobile: str


class LoginFlowMixin:
    """复用登录方式菜单、表单和认证处理。"""

    async def _async_phone_login_form(
        self,
        step_id: str,
        user_input: dict[str, Any] | None,
    ) -> ConfigFlowResult | AuthenticationResult:
        errors: dict[str, str] = {}
        description_placeholders: dict[str, str] = {}

        if user_input is not None:
            try:
                phone = user_input['phone']
                client = HaierClient(self.hass, phone, '', APP_SOURCE_APP)
                token_info = await client.phone_login(
                    phone, user_input['password']
                )
                client = HaierClient(
                    self.hass, phone, token_info.token, APP_SOURCE_APP
                )
                user_info = await client.get_user_info()

                return AuthenticationResult(
                    account={
                        'client_id': phone,
                        'token': token_info.token,
                        'refresh_token': token_info.refresh_token,
                        'expires_at': int(time.time()) + token_info.expires_in,
                        'app_source': APP_SOURCE_APP,
                    },
                    mobile=user_info['mobile']
                )
            except HaierClientException as e:
                _LOGGER.warning(str(e))
                errors['base'] = 'auth_error'
                description_placeholders['reason'] = str(e)

        return self.async_show_form(
            step_id=step_id,
            data_schema=vol.Schema(
                {
                    vol.Required('phone'): str,
                    vol.Required('password'): str,
                }
            ),
            errors=errors,
            description_placeholders=description_placeholders
        )

    async def _async_manual_login_form(
        self,
        step_id: str,
        user_input: dict[str, Any] | None,
        default_client_id: str | None = None,
        default_refresh_token: str | None = None,
        default_app_source: str = DEFAULT_APP_SOURCE,
    ) -> ConfigFlowResult | AuthenticationResult:
        errors: dict[str, str] = {}
        description_placeholders: dict[str, str] = {}

        if user_input is not None:
            try:
                client_id = user_input[CLIENT_ID]
                app_source = user_input[APP_SOURCE]
                client = HaierClient(self.hass, client_id, '', app_source)
                token_info = await client.refresh_token(
                    user_input[REFRESH_TOKEN]
                )
                client = HaierClient(
                    self.hass, client_id, token_info.token, app_source
                )
                user_info = await client.get_user_info()

                return AuthenticationResult(
                    account={
                        'client_id': client_id,
                        'token': token_info.token,
                        'refresh_token': token_info.refresh_token,
                        'expires_at': int(time.time()) + token_info.expires_in,
                        'app_source': app_source,
                    },
                    mobile=user_info['mobile']
                )
            except HaierClientException as e:
                _LOGGER.warning(str(e))
                errors['base'] = 'auth_error'
                description_placeholders['reason'] = str(e)

        client_id_field = (
            vol.Required(CLIENT_ID)
            if default_client_id is None
            else vol.Required(CLIENT_ID, default=default_client_id)
        )
        refresh_token_field = (
            vol.Required(REFRESH_TOKEN)
            if default_refresh_token is None
            else vol.Required(REFRESH_TOKEN, default=default_refresh_token)
        )
        return self.async_show_form(
            step_id=step_id,
            data_schema=vol.Schema(
                {
                    client_id_field: str,
                    refresh_token_field: str,
                    vol.Required(
                        APP_SOURCE, default=default_app_source
                    ): vol.In(APP_SOURCE_OPTIONS),
                }
            ),
            errors=errors,
            description_placeholders=description_placeholders
        )


class HaierConfigFlow(
    LoginFlowMixin, config_entry_oauth2_flow.AbstractOAuth2FlowHandler, domain=DOMAIN
):
    VERSION = CONFIG_ENTRY_VERSION
    DOMAIN = DOMAIN

    def __init__(self) -> None:
        """Initialize the config flow."""
        super().__init__()
        self._region: str = DEFAULT_REGION
        self._language: str = DEFAULT_LANGUAGE
        self._ag_client_id: str = ""
        self._token: dict[str, Any] = {}
        self._auth_implementation: str = ""
        # 重新认证时指向被修复的原条目，为 None 表示添加新账号
        self._reauth_entry: ConfigEntry | None = None

    @property
    def logger(self) -> logging.Logger:
        """Return logger."""
        return _LOGGER

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """选择登录方式"""
        return self.async_show_menu(
            step_id="user",
            menu_options=['oauth', 'phone_login', 'manual']
        )

    async def async_step_oauth(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Handle OAuth authorization."""
        if not supports_oauth2_login():
            _LOGGER.error(
                "oauth login unavailable: state helper missing in this HA version"
            )
            return self.async_abort(reason="oauth_unsupported_ha_version")

        if not self._ag_client_id:
            # 重新认证时沿用原条目的 clientId，避免把账户重新绑到一个新实例上
            if self._reauth_entry is not None:
                cfg = AccountConfig(self.hass, self._reauth_entry)
                if cfg.app_source == APP_SOURCE_OAUTH:
                    self._ag_client_id = cfg.client_id
            if not self._ag_client_id:
                self._ag_client_id = generate_ag_client_id(self._region)

        # 海尔只为这个 client_id 注册了一个回调地址，且换 token 时会逐字符比对。
        # 先用 HA 的对外地址推导一次：不匹配就在这里说清楚，别让用户白跑一趟
        # 授权页再被 invalid_grant 拒掉。
        redirect_uri = get_redirect_uri(self.hass)
        if not is_registered_callback(redirect_uri):
            _LOGGER.warning(
                "oauth redirect mismatch: derived=%s required=%s",
                redirect_uri,
                OAUTH2_CALLBACK_URL,
            )
            return self.async_abort(
                reason="oauth_redirect_mismatch",
                description_placeholders={
                    "current": redirect_uri,
                    "required": OAUTH2_CALLBACK_URL,
                },
            )

        implementation = HaierOAuth2Implementation(
            self.hass, self._ag_client_id, self._region
        )
        async_register_implementation(self.hass, DOMAIN, implementation)

        return await self.async_step_pick_implementation(
            user_input={"implementation": DOMAIN}
        )

    async def async_oauth_create_entry(
        self, data: dict[str, Any]
    ) -> config_entries.ConfigFlowResult:
        """Create config entry after OAuth2 authorization."""
        token = data.get("token")
        if not isinstance(token, dict) or not token.get("access_token"):
            return self.async_abort(reason="get_access_token_error")
        self._token = token
        auth_implementation = data.get("auth_implementation")
        if not isinstance(auth_implementation, str) or not auth_implementation:
            return self.async_abort(reason="auth_implementation_unset")
        self._auth_implementation = auth_implementation

        try:
            account_info = await async_get_account_info(
                self.hass,
                self._region,
                self._ag_client_id,
                self._token["access_token"],
                self._language,
            )

            account = {
                "client_id": self._ag_client_id,
                "token": self._token["access_token"],
                "refresh_token": self._token["refresh_token"],
                "expires_at": int(time.time()) + self._token["expires_in"],
                "app_source": APP_SOURCE_OAUTH,
            }
            # 网页授权只拿得到 userId，账号密码登录拿的是手机号，两者无法换算，
            # 所以条目标题与去重键都用这一侧的标识
            identity = str(account_info["userId"])

            if self._reauth_entry is not None:
                # 重新授权：原地更新原条目，设备、实体与自动化都保留
                self.hass.config_entries.async_update_entry(
                    self._reauth_entry,
                    title="Haier - {}".format(identity),
                    data={
                        **self._reauth_entry.data,
                        "account": account,
                        "identity": identity,
                    },
                )
                return self.async_abort(reason="reauth_successful")

            # 同一账号重复授权时拦下。注意 async_set_unique_id 是 async 方法，
            # 漏掉 await 时协程不会执行，unique_id 恒为 None，去重会静默失效。
            await self.async_set_unique_id(
                "oauth:{}".format(identity), raise_on_progress=False
            )
            self._abort_if_unique_id_configured()

            return self.async_create_entry(
                title="Haier - {}".format(identity),
                data={"account": account, "identity": identity},
            )
        except AbortFlow:
            # 账号已配置的中止要穿透，别被下面的兜底吞成 oauth_token_error
            raise
        except Exception as err:
            _LOGGER.error("Error processing OAuth callback: %s", err, exc_info=True)
            return self.async_abort(reason="oauth_token_error")

    async def async_step_reauth(
        self, entry_data: dict[str, Any]
    ) -> ConfigFlowResult:
        """重新认证：网页授权的 token 过期且续期失败时由 HA 触发。"""
        entry_id = self.context.get("entry_id")
        self._reauth_entry = (
            self.hass.config_entries.async_get_entry(entry_id) if entry_id else None
        )
        return await self.async_step_oauth()

    async def async_step_manual(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        result = await self._async_manual_login_form('manual', user_input)
        if not isinstance(result, AuthenticationResult):
            return result

        return self.async_create_entry(
            title="Haier - {}".format(result.mobile),
            data={
                'account': result.account
            }
        )

    async def async_step_phone_login(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """手机号+密码登录"""
        result = await self._async_phone_login_form('phone_login', user_input)
        if not isinstance(result, AuthenticationResult):
            return result

        return self.async_create_entry(
            title="Haier - {}".format(result.mobile),
            data={
                'account': result.account
            }
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> config_entries.OptionsFlow:
        return OptionsFlowHandler(config_entry)


class OptionsFlowHandler(LoginFlowMixin, config_entries.OptionsFlow):
    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self._config_entry = config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """
        功能菜单
        :param user_input:
        :return:
        """
        return self.async_show_menu(
            step_id="init",
            menu_options=['account', 'device', 'entity_device_selector', 'preferences']
        )

    async def async_step_account( self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """选择账户登录方式。"""
        return self.async_show_menu(
            step_id="account",
            menu_options=['account_oauth', 'account_phone_login', 'account_manual']
        )

    async def async_step_account_oauth(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """改用官方网页授权登录。

        OAuth 回调固定回到 config entry flow，Options 流里接不到，所以这里只
        拉起条目的重新认证流程，让用户回到集成卡片上完成授权。
        """
        self.config_entry.async_start_reauth(self.hass)
        return self.async_abort(reason="reauth_started")

    async def _async_save_account_authentication(
        self, result: AuthenticationResult
    ) -> ConfigFlowResult:
        """保存更新后的账户认证信息。"""
        cfg = AccountConfig(self.hass, self.config_entry)
        cfg.client_id = result.account['client_id']
        cfg.token = result.account['token']
        cfg.refresh_token = result.account['refresh_token']
        cfg.expires_at = result.account['expires_at']
        cfg.app_source = result.account['app_source']
        cfg.save(result.mobile)

        await self.hass.config_entries.async_reload(self.config_entry.entry_id)

        return self.async_create_entry(title='', data={})

    async def async_step_account_phone_login(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """使用手机号和密码更新账户。"""
        result = await self._async_phone_login_form(
            'account_phone_login', user_input
        )
        if not isinstance(result, AuthenticationResult):
            return result

        return await self._async_save_account_authentication(result)

    async def async_step_account_manual(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """使用 Refresh Token 更新账户。"""
        cfg = AccountConfig(self.hass, self.config_entry)
        result = await self._async_manual_login_form(
            'account_manual',
            user_input,
            default_client_id=cfg.client_id,
            default_refresh_token=cfg.refresh_token,
            default_app_source=cfg.app_source
        )
        if not isinstance(result, AuthenticationResult):
            return result

        return await self._async_save_account_authentication(result)

    async def async_step_preferences(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """偏好设置。"""
        cfg = PreferencesConfig(self.hass, self.config_entry)

        if user_input is not None:
            cfg.default_load_all_entity = user_input['default_load_all_entity']
            cfg.ignore_device_offline = user_input['ignore_device_offline']
            cfg.save()

            await self.hass.config_entries.async_reload(self.config_entry.entry_id)

            return self.async_create_entry(title='', data={})

        return self.async_show_form(
            step_id="preferences",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        'default_load_all_entity',
                        default=cfg.default_load_all_entity
                    ): bool,
                    vol.Required(
                        'ignore_device_offline',
                        default=cfg.ignore_device_offline
                    ): bool,
                }
            )
        )

    async def async_step_device(self,  user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
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

    async def async_step_entity_device_selector(self,  user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
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

    async def async_step_entity_filter(self,  user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
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
