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


def random_str(length: int = 32) -> str:
    return ''.join(random.choice('abcdef1234567890') for _ in range(length))


class HaierDeviceGateway:

    def __init__(self, hass: HomeAssistant, client: HaierClient, token: str):
        self._hass = hass
        self._client = client
        self._token = token
        self._session = async_get_clientsession(hass)

    async def connect(self, target_devices: List[HaierDevice]):
        """
        循环监听设备状态
        :param target_devices:  需要监听数据变化的设备
        :return:
        """
        while True:
            try:
                await self._connect(target_devices)
            except asyncio.CancelledError:
                _LOGGER.debug("device gateway stopped")
                return
            except:
                _LOGGER.exception("device gateway disconnected. Waiting to retry.")
                await asyncio.sleep(30)

    async def _connect(self, target_devices: List[HaierDevice]):
        server = await self._client.get_device_gateway()
        _LOGGER.debug('device gateway: {}'.format(server))

        agClientId = self._token
        cancels = []
        try:
            url = '{}/userag?token={}&agClientId={}'.format(server, self._token, agClientId)
            async with self._session.ws_connect(url) as ws:
                _LOGGER.debug('device gateway connected')

                # 订阅设备状态
                await ws.send_str(json.dumps({
                    'agClientId': agClientId,
                    'topic': 'BoundDevs',
                    'content': {
                        'devs': [device.id for device in target_devices]
                    }
                }))

                # 定期发送心跳包
                cancels.append(await self._start_heartbeat_sender(ws, agClientId))

                # 对于部分设备需要定时发送刷新命令以保持数据更新
                force_refresh_devices = [d for d in target_devices if d.product_name in FORCE_REFRESH_PRODUCT_NAMES]
                if force_refresh_devices:
                    cancels.append(
                        await self._start_force_refresh_property_tracker(ws, agClientId, force_refresh_devices)
                    )

                # 监听事件总线来的控制命令
                async def control_callback(e):
                    await self._send_command(ws, agClientId, e.data['deviceId'], e.data['attributes'])

                cancels.append(listen_event(self._hass, EVENT_DEVICE_CONTROL, control_callback))

                # 网关只会在设备数据有变更的时候才会下发数据，所以刚连上网关时需要手动拉取一下数据
                await self._init_devices(target_devices)

                async for msg in ws:
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        await self._parse_message(msg.data)
                    elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.CLOSING):
                        raise RuntimeError("WebSocket 连接已关闭")
                    elif msg.type == aiohttp.WSMsgType.ERROR:
                        raise RuntimeError(f"WebSocket 连接发生异常: {ws.exception()}")
                    else:
                        _LOGGER.warning("收到未知类型的消息: {}".format(msg.type))
        finally:
            fire_event(self._hass, EVENT_GATEWAY_DISCONNECTED, {})
            for cancel in cancels:
                cancel()

    async def _start_heartbeat_sender(self, ws, agClientId: str):
        async def task(now):
            try:
                await ws.send_str(json.dumps({
                    'agClientId': agClientId,
                    'topic': 'HeartBeat',
                    'content': {
                        'sn': random_str(32),
                        'duration': 0
                    }
                }))

                _LOGGER.debug('Sending heartbeat')
            except Exception:
                _LOGGER.exception('Failed to send heartbeat')

        return async_track_time_interval(self._hass, task, timedelta(seconds=60))

    async def _start_force_refresh_property_tracker(self, ws, agClientId: str, devices: List[HaierDevice]):
        async def task(now):
            for device in devices:
                try:
                    await self._send_command(ws, agClientId, device.id, {'getAllProperty': 'getAllProperty'})
                    _LOGGER.debug('Sent force refresh command to device: %s', device.id)
                except Exception:
                    _LOGGER.exception('Failed to send force refresh to device: %s', device.id)

        return async_track_time_interval(self._hass, task, timedelta(seconds=60))

    async def _init_devices(self, target_devices: List[HaierDevice]):
        device_online_statues = await self._client.get_devices_online_status()

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

        await asyncio.gather(*[_fetch_snapshot(d) for d in target_devices], return_exceptions=True)

    async def _parse_message(self, msg):
        msg = json.loads(msg)
        if msg['topic'] != 'GenMsgDown':
            _LOGGER.debug('Received websocket data: ' + json.dumps(msg))
            return

        # {
        #     "agClientId": "xxxxxxx",
        #     "topic": "GenMsgDown",
        #     "content": {
        #         "businType": "DigitalModel",
        #         "data": "base64...",
        #         "dataFmt": "",
        #         "sn": "xxxxxxxxx"
        #     }
        # }

        data = base64.b64decode(msg['content']['data'])
        data = json.loads(data)

        # 设备attributes数据变动
        if msg['content']['businType'] == 'DigitalModel':
            await self._process_digital_model(data)
            return

        # 设备在线/离线监听
        if msg['content']['businType'] in ('DevOfflineNotify', 'DevOnlineNotify'):
            for device_id in data['devs']:
                fire_event(self._hass, EVENT_DEVICE_ONLINE_CHANGED, {
                    'deviceId': device_id,
                    'online': msg['content']['businType'] == 'DevOnlineNotify'
                })
            return

        _LOGGER.debug('Received websocket data: ' + json.dumps(msg))

    async def _process_digital_model(self, data):
        # {
        #     "args": "xxxxxxx",
        #     "dev": "deviceId.."
        # }
        deviceId = data['dev']
        data = zlib.decompress(base64.b64decode(data['args']), 16 + zlib.MAX_WBITS)
        data = json.loads(data.decode('utf-8'))

        # {
        #     "alarms": [],
        #     "attributes": [
        #         {
        #             "defaultValue": "35",
        #             "desc": "目标温度",
        #             "invisible": false,
        #             "name": "targetTemp",
        #             "operationType": "IG",
        #             "readable": true,
        #             "value": "40",
        #             "valueRange": {
        #                 "dataStep": {
        #                     "dataType": "Integer",
        #                     "maxValue": "60",
        #                     "minValue": "35",
        #                     "step": "1"
        #                 },
        #                 "type": "STEP"
        #             },
        #             "writable": true
        #         }
        #         ....
        #     ],
        #     "businessAttr": []
        # }
        attributes = {}
        for attribute in data['attributes']:
            # 有些attribute没有value字段。。。
            if 'value' not in attribute:
                continue

            attributes[attribute['name']] = attribute['value']

        fire_event(self._hass, EVENT_DEVICE_DATA_CHANGED, {
            'deviceId': deviceId,
            'attributes': attributes
        })

    @staticmethod
    async def _send_command(ws, agClientId, deviceId: str, attributes: dict):
        """
        通过websocket发送控制命令
        :param ws:
        :param agClientId:
        :param deviceId: 设备ID
        :param attributes: 获取设备attributes (如: { "targetTemp": "42" })
        :return:
        """
        sn = random_str(32)
        await ws.send_str(json.dumps({
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
        }))
