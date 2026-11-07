"""海尔云端接入层。

只包含「接入阶段」需要的东西：

* :func:`async_get_account_info` -- 拿到 token 后读一次账户 userId。
* :class:`HaierOAuth2Implementation` -- 授权页登录的 OAuth2 适配。
* :func:`generate_ag_client_id` -- 生成每次安装唯一的 clientId。

运行期的设备、家庭、场景接口在 ``core/client.py`` 的 ``HaierClient``，不要在
这里再实现一份。
"""

from .http_client import HaierAPIError, async_get_account_info
from .oauth2 import HaierOAuth2Implementation
from .utils import generate_ag_client_id

__all__ = [
    "HaierAPIError",
    "HaierOAuth2Implementation",
    "async_get_account_info",
    "generate_ag_client_id",
]
