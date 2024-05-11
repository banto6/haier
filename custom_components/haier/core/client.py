import asyncio
import base64
import hashlib
import json
import logging
import random
import threading
import time
import zlib
from typing import List
from urllib.parse import urlparse

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import EVENT_DEVICE_CONTROL, EVENT_DEVICE_DATA_CHANGED, EVENT_WSS_GATEWAY_STATUS_CHANGED
from .device import HaierDevice

_LOGGER = logging.getLogger(__name__)

APP_ID = 'MB-SHEZJAPPWXXCX-0000'
APP_KEY = '79ce99cc7f9804663939676031b8a427'
APP_VERSION = '5.3.0'

GET_USER_INFO_API = 'https://account-api.haier.net/v2/haier/userinfo'
GET_DEVICES_API = 'https://uws.haier.net/uds/v1/protected/deviceinfos'
GET_WSS_GW_API = 'https://uws.haier.net/gmsWS/wsag/assign'
GET_DIGITAL_MODEL_API = 'https://uws.haier.net/shadow/v1/devdigitalmodels'


def random_str(length: int = 32) -> str:
    return ''.join(random.choice('abcdef1234567890') for _ in range(length))

class HaierClientException(Exception):
    pass


class HaierClient:

    def __init__(self, hass: HomeAssistant, client_id: str, token: str):
        self._client_id = client_id
        self._token = token
        self._hass = hass
        self._session = async_get_clientsession(hass)

    @property
    def hass(self):
        return self._hass

    async def get_user_info(self) -> dict:
        """
        根据token获取用户信息
        :return:
        """
        headers = {
            'Authorization': f'Bearer {self._token}',
        }
        async with self._session.get(url=GET_USER_INFO_API, headers=headers) as response:
            content = await response.json(content_type=None)
            if 'error_description' in content:
                raise HaierClientException('Error getting user info, error: {}'.format(content['error_description']))

            return {
                'userId': content['userId'],
                'mobile': content['mobile'],
                'username': content['username']
            }

    async def get_devices(self) -> List[HaierDevice]:
        """
        获取设备列表
        """
        headers = await self._generate_common_headers(GET_DEVICES_API)
        async with self._session.get(url=GET_DEVICES_API, headers=headers) as response:
            content = await response.json(content_type=None)
            self._assert_response_successful(content)

            devices = []
            for raw in content['deviceinfos']:
                _LOGGER.debug('Device Info: {}'.format(raw))
                device = HaierDevice(self, raw)
                await device.async_init()
                devices.append(device)

            return devices

    async def get_digital_model(self, deviceId: str) -> list:
        """
        获取设备attributes
        :param deviceId:
        :return:
        """
        payload = {
            'deviceInfoList': [
                {
                    'deviceId': deviceId
                }
            ]
        }

        headers = await self._generate_common_headers(GET_DIGITAL_MODEL_API, json.dumps(payload))
        async with self._session.post(url=GET_DIGITAL_MODEL_API, json=payload, headers=headers) as response:
            content = await response.json(content_type=None)
            self._assert_response_successful(content)

            if deviceId not in content['detailInfo']:
                _LOGGER.warning("Device {} get digital model fail. response: {}".format(
                    deviceId,
                    json.dumps(content, ensure_ascii=False)
                ))
                return []

            return json.loads(content['detailInfo'][deviceId])['attributes']

    async def listen_devices(self, targetDevices: List[HaierDevice]):
        """

        :param targetDevices: 需要监听数据变化的设备
        :return:
        """
        server = await self._get_wss_gateway_url()

        _LOGGER.debug("WSSGateway: %s", server)

        # https://docs.aiohttp.org/en/stable/client_quickstart.html#aiohttp-client-websockets
        agClientId = self._token
        while True:
            url = '{}/userag?token={}&agClientId={}'.format(server, self._token, agClientId)
            async with self._session.ws_connect(url) as ws:
                try:
                    # 每60秒发送一次心跳包
                    event = threading.Event()
                    self._hass.async_create_background_task(self._send_heartbeat(ws, agClientId, event), 'haier-wss-send_heartbeat')

                    # 订阅设备状态
                    await ws.send_str(json.dumps({
                        'agClientId': agClientId,
                        'topic': 'BoundDevs',
                        'content': {
                            'devs': [device.id for device in targetDevices]
                        }
                    }))

                    # 监听事件总线来的控制命令
                    async def control_callback(e):
                        await self._send_command(ws, agClientId, e.data['deviceId'], e.data['attributes'])
                    cancel_control_listen = self._hass.bus.async_listen(EVENT_DEVICE_CONTROL, control_callback)

                    self._hass.bus.fire(EVENT_WSS_GATEWAY_STATUS_CHANGED, {
                        'status': True
                    })

                    async for msg in ws:
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            await self._parse_message(msg.data)
                        else:
                            _LOGGER.warning("收到未知类型的消息: {}".format(msg.type))
                finally:
                    cancel_control_listen()
                    event.set()
                    self._hass.bus.fire(EVENT_WSS_GATEWAY_STATUS_CHANGED, {
                        'status': False
                    })

            _LOGGER.debug("Connection disconnected. Waiting to retry.")
            await asyncio.sleep(30)

    @staticmethod
    async def _send_heartbeat(ws, agClientId: str, event: threading.Event):
        while True:
            if event.is_set():
                _LOGGER.info("Stop heartbeat...")
                break

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
            except:
                _LOGGER.error('Failed to send heartbeat')

            await asyncio.sleep(60)

    async def _parse_message(self, msg):
        msg = json.loads(msg)
        # 目前只关注设备attributes数据变动的消息，所以其他消息暂不处理
        if msg['topic'] != 'GenMsgDown':
            _LOGGER.debug('Received websocket data: ' + json.dumps(msg))
            return

        # 不确定是否其他类型，以防万一先做个判断
        if msg['content']['businType'] != 'DigitalModel':
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

        self._hass.bus.async_fire(EVENT_DEVICE_DATA_CHANGED, {
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

    async def _get_wss_gateway_url(self) -> str:
        """
        获取网关地址
        :return:
        """
        payload = {
            'clientId': self._client_id,
            'token': self._token
        }

        headers = await self._generate_common_headers(GET_WSS_GW_API, json.dumps(payload))
        async with self._session.post(url=GET_WSS_GW_API, json=payload, headers=headers) as response:
            content = await response.json(content_type=None)
            self._assert_response_successful(content)

            return content['agAddr'].replace('http://', 'wss://')

    async def _generate_common_headers(self, api, body=''):
        """
        返回通用headers
        :param api:
        :param body:
        :return:
        """
        timestamp = str(int(time.time() * 1000))
        # 报文流水(客户端唯一)客户端交易流水号。20位,
        # 前14位时间戳（格式：yyyyMMddHHmmss）,
        # 后6位流水号。交易发生时,根据交易 笔数自增量。App应用访问uws接口时必须确保每次请求唯一，不能重复。
        sequence_id = time.strftime('%Y%m%d%H%M%S') + str(random.randint(100000, 999999))

        return {
            'accessToken': self._token,
            'appId': APP_ID,
            'appKey': APP_KEY,
            'appVersion': APP_VERSION,
            'clientId': self._client_id,
            'sequenceId': sequence_id,
            'sign': self._sign(APP_ID, APP_KEY, timestamp, body, api),
            'timestamp': timestamp,
            'timezone': '+8',
            'language': 'zh-CN'
        }

    @staticmethod
    def _assert_response_successful(resp):
        if 'retCode' in resp and resp['retCode'] != '00000':
            raise HaierClientException('接口返回异常: ' + resp['retInfo'])

    @staticmethod
    def _sign(app_id, app_key, timestamp, body, url):
        content = urlparse(url).path \
                  + str(body).replace('\t', '').replace('\r', '').replace('\n', '').replace(' ', '') \
                  + str(app_id) \
                  + str(app_key) \
                  + str(timestamp)

        return hashlib.sha256(content.encode('utf-8')).hexdigest()
