"""单个配置条目的运行时状态。

这些数据以前放在 ``hass.data[DOMAIN]`` 里。``hass.data`` 的顶层键是 domain
而不是 entry_id，多个条目会共用同一块字典：后加载的条目覆盖前者的设备列表
与任务槽位，卸载任一条目还会把整块数据删掉，另一个条目的实体随即 KeyError。
改挂到 ``entry.runtime_data`` 之后，每个条目一份，生命周期跟随条目本身。
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .client import HaierClient
    from .device import HaierDevice
    from .device_gateway import HaierDeviceGateway


@dataclass
class HaierRuntimeData:
    """一个配置条目的运行时状态。"""

    # 条目标识。事件总线是全局的，收发事件时靠它区分是哪个条目
    entry_id: str
    client: HaierClient
    devices: list[HaierDevice]
    gateway: HaierDeviceGateway
    # 是否忽略设备离线状态，供实体在收到离线事件时判断是否保留最后状态
    ignore_device_offline: bool
    # 停止定时刷新 token 的回调
    cancel_token_updater: Callable[[], None] | None = None
    # 网关后台任务，条目卸载时取消
    gateway_task: asyncio.Task | None = field(default=None)
