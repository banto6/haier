"""接入阶段要用到的海尔云端 REST 接口。

网页授权登录在拿到 token 后需要读一次账户信息（userId）来生成条目标题、
计算去重键，这就是本模块的全部职责。

设备、家庭、场景等运行期接口由 ``core/client.py`` 的 ``HaierClient`` 负责，
不要在这里重复实现一份——两套客户端并存只会让以后改接口时漏掉一边。
"""

import logging
import time
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from ..const import (
    API_ENDPOINT_MAP,
    API_HOSTS_MAP,
    APP_ID,
    APP_VERSION,
    DEFAULT_LANGUAGE,
)

_LOGGER = logging.getLogger(__name__)


class HaierAPIError(Exception):
    """海尔接口返回业务错误（``retCode`` 不是 ``00000``）。"""

    def __init__(
        self, error_code: str | None = None, error_message: str | None = None
    ) -> None:
        self.error_code = error_code
        self.error_message = error_message
        super().__init__(str(self))

    def __str__(self) -> str:
        if self.error_code and self.error_message:
            return f"Haier API request failed [{self.error_code}]: {self.error_message}"
        if self.error_code:
            return f"Haier API request failed [{self.error_code}]"
        return "Haier API request failed"


async def async_get_account_info(
    hass: HomeAssistant,
    region: str,
    ag_client_id: str,
    access_token: str,
    language: str = DEFAULT_LANGUAGE,
) -> dict[str, Any]:
    """读取当前授权账号的账户信息。

    这个接口不参与 appId/appKey 签名，带 ``accessToken`` 即可。

    :param hass: Home Assistant 实例（复用 HA 的 aiohttp 会话）
    :param region: 区域键，用来选 API 主机
    :param ag_client_id: 授权时生成的实例标识，作为 ``clientId`` 请求头
    :param access_token: OAuth 换回来的 access token
    :param language: ``Accept-Language``
    :return: 响应里的 ``data``，至少包含 ``userId``
    :raises HaierAPIError: 接口返回非 ``00000`` 的 ``retCode``
    """
    url = "https://{}{}".format(
        API_HOSTS_MAP[region], API_ENDPOINT_MAP["account_info"]
    )
    headers = {
        "Connection": "keep-alive",
        "Content-Type": "application/json;charset=utf-8",
        "appId": APP_ID,
        "appVersion": APP_VERSION,
        "clientId": ag_client_id,
        "accessToken": access_token,
        "Accept-Language": language,
        "timestamp": str(int(time.time() * 1000)),
        "User-Agent": "Apache-HttpClient/4.5.14 (Java/1.8.0_442)",
    }

    session = async_get_clientsession(hass)
    async with session.get(url, headers=headers) as resp:
        # 先看 HTTP 状态，免得非 JSON 的错误页被 JSONDecodeError 盖掉真正的原因
        resp.raise_for_status()
        result = await resp.json()

    if result.get("retCode") != "00000":
        raise HaierAPIError(result.get("retCode"), result.get("retInfo"))

    _LOGGER.debug("Fetched Haier account info from %s", API_ENDPOINT_MAP["account_info"])
    return result.get("data") or {}
