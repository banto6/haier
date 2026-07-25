import asyncio
import base64
import json
import logging
import random
import zlib
from datetime import timedelta
from typing import List

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_time_interval

from .client import HaierClient
from .device import HaierDevice
from .event import EVENT_DEVICE_CONTROL, EVENT_DEVICE_DATA_CHANGED, EVENT_GATEWAY_DISCONNECTED, \
    EVENT_DEVICE_ONLINE_CHANGED
from .event import listen_event, fire_event

_LOGGER = logging.getLogger(__name__)

FORCE_REFRESH_PRODUCT_NAMES = [
    'JSQ30-16R3BWU1'
]

FORCE_REFRESH_PRODUCT_PREFIXES = [
    'KFR-'       # 海尔空调产品型号通常以 KFR- 开头
]


def _should_force_refresh(product_name: str) -> bool:
    """判断设备是否需要强制轮询刷新数据"""
    if product_name in FORCE_REFRESH_PRODUCT_NAMES:
        return True
    for prefix in FORCE_REFRESH_PRODUCT_PREFIXES:
        if product_name.startswith(prefix):
            return True
    return False


def random_str(length: int = 32) -> str:
    return ''.join(random.choice('abcdef1234567890') for _ in range(length))


class HaierDeviceGateway:

    def __init__(self, hass: HomeAssistant, client: HaierClient, token: str):
        self._hass = hass
        self._client = client
        self._token = token
        self._session = async_get_clientsession(hass)
        self._ws_lock = asyncio.Lock()
        self._pending_commands: asyncio.Queue = asyncio.Queue()

    async def connect(self, target_devices: List[HaierDevice]):
        """
        循环监听设备状态
        :param target_devices:  需要监听数据变化的设备
        :return:
        """
        retry_delay = 5
        max_retry_delay = 60
        retry_count = 0
        consecutive_failures = 0
        token_expiry_warning_threshold = 5
        while True:
            try:
                retry_count += 1
                if retry_count > 1:
                    _LOGGER.info(
                        "Attempting to reconnect WebSocket (attempt #%s, delay=%ss)",
                        retry_count, retry_delay
                    )
                await self._connect(target_devices)
                # 连接成功后重置退避延迟和重试计数
                retry_delay = 5
                retry_count = 0
                consecutive_failures = 0
            except asyncio.CancelledError:
                _LOGGER.debug("device gateway stopped")
                return
            except Exception:
                consecutive_failures += 1
                _LOGGER.exception(
                    "device gateway disconnected (attempt #%s, consecutive failures: %s). Retrying in %s seconds.",
                    retry_count, consecutive_failures, retry_delay
                )
                if consecutive_failures >= token_expiry_warning_threshold:
                    _LOGGER.error(
                        "WebSocket 已连续 %s 次重连失败，Token 可能已过期。"
                        "如果问题持续，请在 HA 中手动重载此集成以刷新 Token。",
                        consecutive_failures
                    )
                await asyncio.sleep(retry_delay)
                retry_delay = min(retry_delay * 2, max_retry_delay)

    async def _connect(self, target_devices: List[HaierDevice]):
        server = await self._client.get_device_gateway()
        _LOGGER.debug('device gateway: {}'.format(server))

        agClientId = self._token
        cancels = []
        try:
            url = '{}/userag?token={}&agClientId={}'.format(server, self._token, agClientId)
            async with self._session.ws_connect(url, heartbeat=30) as ws:
                _LOGGER.info('WebSocket connected to device gateway (device count: %s)', len(target_devices))

                # 订阅设备状态
                await self._ws_send_str(ws, {
                    'agClientId': agClientId,
                    'topic': 'BoundDevs',
                    'content': {
                        'devs': [device.id for device in target_devices]
                    }
                })

                # 定期发送心跳包
                cancels.append(await self._start_heartbeat_sender(ws, agClientId))

                # 对于部分设备需要定时发送刷新命令以保持数据更新
                force_refresh_devices = [d for d in target_devices if _should_force_refresh(d.product_name)]
                if force_refresh_devices:
                    cancels.append(
                        await self._start_force_refresh_property_tracker(ws, agClientId, force_refresh_devices)
                    )

                # 监听事件总线来的控制命令
                async def control_callback(e):
                    device_id = e.data.get('deviceId')
                    attributes = e.data.get('attributes', {})
                    if not device_id:
                        _LOGGER.warning('Invalid control event, missing deviceId: %s', e.data)
                        return
                    try:
                        await self._send_command(ws, agClientId, device_id, attributes)
                    except Exception:
                        _LOGGER.exception('Failed to send command via WebSocket, queuing for retry')
                        await self._pending_commands.put({
                            'deviceId': device_id,
                            'attributes': attributes
                        })
                        await ws.close()

                cancels.append(listen_event(self._hass, EVENT_DEVICE_CONTROL, control_callback))

                # 网关只会在设备数据有变更的时候才会下发数据，所以刚连上网关时需要手动拉取一下数据
                await self._init_devices(target_devices)

                # 发送重连前排队未送达的控制命令
                await self._drain_pending_commands(ws, agClientId)

                async for msg in ws:
                    try:
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            await self._parse_message(msg.data)
                        elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.CLOSING):
                            raise RuntimeError("WebSocket 连接已关闭")
                        elif msg.type == aiohttp.WSMsgType.ERROR:
                            raise RuntimeError(f"WebSocket 连接发生异常: {ws.exception()}")
                        else:
                            _LOGGER.warning("收到未知类型的消息: {}".format(msg.type))
                    except RuntimeError:
                        raise
                    except Exception:
                        _LOGGER.exception('Unexpected error in WebSocket message loop, skipping message')
        finally:
            fire_event(self._hass, EVENT_GATEWAY_DISCONNECTED, {})
            for cancel in cancels:
                cancel()

    async def _ws_send_str(self, ws, data: dict):
        """
        线程安全地发送 WebSocket 消息，使用锁防止并发写入导致帧交错
        :param ws: WebSocket 连接
        :param data: 要发送的字典数据，会被 JSON 序列化
        """
        async with self._ws_lock:
            await ws.send_str(json.dumps(data))

    async def _start_heartbeat_sender(self, ws, agClientId: str):
        async def task(now):
            try:
                await self._ws_send_str(ws, {
                    'agClientId': agClientId,
                    'topic': 'HeartBeat',
                    'content': {
                        'sn': random_str(32),
                        'duration': 0
                    }
                })

                _LOGGER.debug('Sending heartbeat')
            except Exception:
                _LOGGER.exception('Failed to send heartbeat, closing WebSocket')
                await ws.close()

        return async_track_time_interval(self._hass, task, timedelta(seconds=60))

    async def _start_force_refresh_property_tracker(self, ws, agClientId: str, devices: List[HaierDevice]):
        async def task(now):
            for device in devices:
                try:
                    await self._send_command(ws, agClientId, device.id, {'getAllProperty': 'getAllProperty'})
                    _LOGGER.debug('Sent force refresh command to device: %s', device.id)
                except Exception:
                    _LOGGER.exception('Failed to send force refresh to device: %s, closing WebSocket', device.id)
                    await ws.close()
                    return

        return async_track_time_interval(self._hass, task, timedelta(seconds=60))

    async def _drain_pending_commands(self, ws, agClientId):
        """
        发送所有排队中的控制命令，在重连后调用。
        单个命令失败不会影响后续命令的处理。
        """
        while not self._pending_commands.empty():
            try:
                cmd = await self._pending_commands.get()
                await self._send_command(ws, agClientId, cmd['deviceId'], cmd['attributes'])
                _LOGGER.info('Retried queued command to device %s', cmd['deviceId'])
            except Exception:
                _LOGGER.exception('Failed to retry queued command to device %s, dropping it', cmd.get('deviceId', 'unknown'))
                # 命令已从队列取出，失败后不再重新入队，避免阻塞后续命令

    async def _init_devices(self, target_devices: List[HaierDevice]):
        device_online_statues = await self._client.get_devices_online_status()

        for device in target_devices:
            if device_online_statues.get(device.id) is False:
                fire_event(self._hass, EVENT_DEVICE_ONLINE_CHANGED, {
                    'deviceId': device.id,
                    'online': False
                })

        async def _fetch_snapshot(device):
            # 跳过已离线的设备
            if device.id in device_online_statues and device_online_statues[device.id] is False:
                return

            _LOGGER.debug("Fetching snapshot data for device: %s", device.id)

            snapshot_data = await self._client.get_device_snapshot_data(device.id)
            fire_event(self._hass, EVENT_DEVICE_DATA_CHANGED, {
                'deviceId': device.id,
                'attributes': snapshot_data
            })

        async def _fetch_snapshot_safely(device):
            try:
                await _fetch_snapshot(device)
            except Exception:
                _LOGGER.exception("Failed to fetch initial snapshot for device: %s", device.id)

        await asyncio.gather(*[_fetch_snapshot_safely(d) for d in target_devices])

    async def _parse_message(self, msg):
        try:
            msg = json.loads(msg)
            if msg.get('topic') != 'GenMsgDown':
                # 记录命令响应（如 BatchCmdReq 的回复）便于诊断
                topic_lower = str(msg.get('topic', '')).lower()
                if 'batchcmd' in topic_lower or 'batch' in topic_lower or 'cmd' in topic_lower:
                    _LOGGER.info('Received command response via WebSocket: %s', json.dumps(msg, ensure_ascii=False))
                else:
                    _LOGGER.debug('Received websocket data: %s', json.dumps(msg, ensure_ascii=False))
                return

            content = msg.get('content', {})
            if not content or 'data' not in content:
                _LOGGER.warning('Received GenMsgDown without content.data: %s', json.dumps(msg, ensure_ascii=False))
                return

            data = base64.b64decode(content['data'])
            data = json.loads(data)

            # 设备attributes数据变动
            if content.get('businType') == 'DigitalModel':
                await self._process_digital_model(data)
                return

            # 设备在线/离线监听
            if content.get('businType') in ('DevOfflineNotify', 'DevOnlineNotify'):
                for device_id in data.get('devs', []):
                    online = content['businType'] == 'DevOnlineNotify'
                    fire_event(self._hass, EVENT_DEVICE_ONLINE_CHANGED, {
                        'deviceId': device_id,
                        'online': online
                    })
                    _LOGGER.info('Device %s is %s', device_id, 'Online' if online else 'Offline')
                return

            _LOGGER.debug('Received websocket data: ' + json.dumps(msg))
        except Exception:
            _LOGGER.exception('Failed to parse WebSocket message: %s', msg if isinstance(msg, str) else str(msg)[:500])

    async def _process_digital_model(self, data):
        deviceId = data.get('dev')
        if not deviceId:
            _LOGGER.warning('DigitalModel message missing dev field: %s', data)
            return

        try:
            raw = zlib.decompress(base64.b64decode(data['args']), 16 + zlib.MAX_WBITS)
            data = json.loads(raw.decode('utf-8'))
        except Exception:
            _LOGGER.exception('Failed to decompress/decode DigitalModel for device %s', deviceId)
            return

        attributes = {}
        for attribute in data.get('attributes', []):
            # 有些attribute没有value字段。。。
            if 'value' not in attribute:
                continue

            attributes[attribute['name']] = attribute['value']

        fire_event(self._hass, EVENT_DEVICE_DATA_CHANGED, {
            'deviceId': deviceId,
            'attributes': attributes
        })

    async def _send_command(self, ws, agClientId, deviceId: str, attributes: dict):
        """
        通过websocket发送控制命令
        :param ws:
        :param agClientId:
        :param deviceId: 设备ID
        :param attributes: 获取设备attributes (如: { "targetTemp": "42" })
        :return:
        """
        sn = random_str(32)
        await self._ws_send_str(ws, {
            'agClientId': agClientId,
            "topic": "BatchCmdReq",
            'content': {
                'trace': random_str(32),
                'sn': sn,
                'data': [
                    {
                        'sn': sn,
                        'index': 0,
                        'delaySeconds': 0,
                        'subSn': sn + ':0',
                        'deviceId': deviceId,
                        'cmdArgs': attributes
                    }
                ]
            }
        })
