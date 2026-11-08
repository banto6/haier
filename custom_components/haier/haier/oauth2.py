"""海尔授权页登录的 OAuth2 实现。

只负责两件事：拼授权链接、用 code 换 token。token 的日常续期由
``core/client.py`` 的 ``HaierClient.oauth_refresh_token()`` 负责（走的是同一
个签发端点），这里保留的 ``_async_refresh_token`` 只是为了满足 HA 抽象基类的
要求——若将来改用 ``OAuth2Session`` 才会走到它。
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any
from urllib.parse import urlencode

from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_entry_oauth2_flow
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.network import NoURLAvailableError, get_url

# HA 没有公开的 state 编解码接口，但 /auth/external/callback 视图要求 state
# 必须能被它自己的 _decode_jwt 解开，所以只能复用这个内部函数。HA 内置的
# LocalOAuth2Implementation.async_generate_authorize_url() 也是同款做法。
# 这里做防御性导入：万一将来被改名或移除，让配置流程提示“当前版本不支持网页
# 授权”，而不是在用户点授权按钮时抛一个界面上看不懂的异常。
try:
    from homeassistant.helpers.config_entry_oauth2_flow import _encode_jwt
except ImportError:  # pragma: no cover - 依赖 HA 内部实现
    _encode_jwt = None

from ..const import (
    API_ENDPOINT_MAP,
    API_HOSTS_MAP,
    APP_ID,
    APP_VERSION,
    DOMAIN,
    OAUTH2_AUTH_URL,
    OAUTH2_CALLBACK_PATH,
    OAUTH2_CALLBACK_URL,
    OAUTH2_CLIENT_ID,
)
from .http_client import HaierAPIError
from .utils import mask_token, validate_construct_token

_LOGGER = logging.getLogger(__name__)


def supports_oauth2_login() -> bool:
    """当前 HA 版本能否生成合规的授权链接。

    :return: 内部辅助函数可用时为 True
    """
    return _encode_jwt is not None


def get_redirect_uri(hass: HomeAssistant) -> str:
    """按 HA 的对外访问地址动态推导 OAuth 回调地址。

    海尔只注册了一个回调值（见 ``OAUTH2_CALLBACK_URL``），且换 token 时会逐字符
    比对。所以回调地址不能写死成某个主机名：换个部署环境（改端口、换域名、
    容器里换主机名）就会在 code 换 token 那一步被 ``invalid_grant`` 拒掉。

    这里优先用 ``external_url``，没有配置时回落到 HA 探测到的 ``internal_url``
    （Home Assistant OS 默认安装就是 ``http://homeassistant.local:8123``），
    两者都拿不到时回落到注册值本身。

    :param hass: Home Assistant 实例
    :return: 完整的回调地址
    """
    try:
        base_url = get_url(
            hass,
            prefer_external=True,
            allow_internal=True,
            allow_cloud=False,
            allow_ip=True,
        )
    except NoURLAvailableError:
        _LOGGER.debug("no HA url available, fall back to registered callback")
        return OAUTH2_CALLBACK_URL

    return f"{base_url.rstrip('/')}{OAUTH2_CALLBACK_PATH}"


def is_registered_callback(redirect_uri: str) -> bool:
    """判断回调地址是否与海尔注册值一致。

    服务端做的是逐字符比较，这里保持一致（只容忍末尾斜杠差异）。

    :param redirect_uri: 待校验的回调地址
    :return: 是否可用
    """
    return redirect_uri.rstrip("/") == OAUTH2_CALLBACK_URL.rstrip("/")


async def async_request_token(
    hass: HomeAssistant,
    region: str,
    ag_client_id: str,
    body: dict[str, Any],
    endpoint: str,
    error_default: str,
) -> dict[str, Any]:
    """向签发端点换/续 token。

    这个端点不参与 appId/appKey 签名，带 ``appId``/``clientId`` 请求头即可。

    :param hass: Home Assistant 实例
    :param region: 区域键，用来选 API 主机
    :param ag_client_id: 授权时生成的实例标识，作为 ``clientId``
    :param body: 请求体
    :param endpoint: ``API_ENDPOINT_MAP`` 里的键
    :param error_default: 接口没给 retInfo 时的兜底错误描述
    :return: 规范化后的 token 字典
    """
    url = f"https://{API_HOSTS_MAP[region]}{API_ENDPOINT_MAP[endpoint]}"
    headers = {
        "Connection": "keep-alive",
        "Content-Type": "application/json;charset=utf-8",
        "appId": APP_ID,
        "appVersion": APP_VERSION,
        "clientId": ag_client_id,
        "Accept-Language": "zh",
        "timestamp": str(int(time.time() * 1000)),
        "User-Agent": "Apache-HttpClient/4.5.14 (Java/1.8.0_442)",
    }

    session = async_get_clientsession(hass)
    async with session.post(url, data=json.dumps(body), headers=headers) as resp:
        # 先看 HTTP 状态，免得非 JSON 的错误页被 JSONDecodeError 盖掉真正的原因
        resp.raise_for_status()
        result = await resp.json()

    if result.get("retCode") != "00000":
        raise HaierAPIError(result.get("retCode"), result.get("retInfo", error_default))

    token = validate_construct_token(result.get("data") or {})
    _LOGGER.debug(
        "token obtained from %s: %s (region=%s)",
        endpoint,
        mask_token(token.get("access_token")),
        region,
    )
    return token


class HaierOAuth2Implementation(config_entry_oauth2_flow.AbstractOAuth2Implementation):
    """海尔授权页登录的实现。"""

    def __init__(self, hass: HomeAssistant, ag_client_id: str, region: str) -> None:
        """Initialize the implementation."""
        self.hass = hass
        self._domain = DOMAIN
        self._region = region
        self._ag_client_id = ag_client_id

    @property
    def name(self) -> str:
        """Name of the implementation."""
        return f"Haier Home ({self._region})"

    @property
    def domain(self) -> str:
        """Domain that is providing the implementation."""
        return self._domain

    @property
    def client_id(self) -> str:
        """Client ID of this installation."""
        return self._ag_client_id

    @property
    def authorize_url(self) -> str:
        """Authorize URL."""
        return OAUTH2_AUTH_URL

    @property
    def token_url(self) -> str:
        """Token URL."""
        return (
            f"https://{API_HOSTS_MAP[self._region]}{API_ENDPOINT_MAP['token']}"
        )

    @property
    def redirect_uri(self) -> str:
        """Redirect URI, derived from HA's own external/internal URL."""
        return get_redirect_uri(self.hass)

    async def async_generate_authorize_url(self, flow_id: str) -> str:
        """拼授权链接。

        注意这里有两个不同的 client id，别把它们合并：
        * ``client_id`` 参数是海尔的 OAuth 应用标识（``SV-…``），授权页只认它；
        * 换 token 时的 ``clientId`` 是本次安装的实例标识（``HA…``），
          由 ``async_resolve_external_data`` 带上，签发出来的 token 与它绑定。
        """
        if _encode_jwt is None:
            # 正常路径下 config_flow 已在跳转前用 supports_oauth2_login() 拦过
            raise RuntimeError(
                "this Home Assistant version does not expose the OAuth state helper"
            )

        # state 由 HA 签发，回调时会带回来校验，避免 CSRF
        state = _encode_jwt(
            self.hass, {"flow_id": flow_id, "redirect_uri": self.redirect_uri}
        )
        params = {
            "redirect_uri": self.redirect_uri,
            "client_id": OAUTH2_CLIENT_ID,
            "response_type": "code",
            "state": state,
        }
        return f"{self.authorize_url}?{urlencode(params)}"

    async def async_resolve_external_data(
        self, external_data: dict[str, Any]
    ) -> dict[str, Any]:
        """用授权码换 token。"""
        code = external_data.get("code")
        if not code:
            raise ValueError("Missing 'code' in OAuth callback data")

        _LOGGER.debug("Resolving OAuth authorization code for region %s", self._region)

        return await async_request_token(
            self.hass,
            self._region,
            self._ag_client_id,
            {
                "code": code,
                "clientId": self._ag_client_id,
                "redirectUri": self.redirect_uri,
                "grantType": "authorization_code",
            },
            "token",
            "Token request failed",
        )

    async def _async_refresh_token(self, token: dict[str, Any]) -> dict[str, Any]:
        """用 refresh_token 续期。

        抽象基类要求实现，但本集成实际走 ``HaierClient.oauth_refresh_token()``
        （见 core/client.py）。两处打的是同一个端点，改接口时都要看。
        """
        refresh_token = token.get("refresh_token")
        if not refresh_token:
            raise ValueError("No refresh token available")

        _LOGGER.debug("Refreshing OAuth token for region %s", self._region)

        return await async_request_token(
            self.hass,
            self._region,
            self._ag_client_id,
            {
                "refreshToken": refresh_token,
                "clientId": self._ag_client_id,
                "grantType": "refresh_token",
            },
            "refresh_token",
            "Token refresh failed",
        )
