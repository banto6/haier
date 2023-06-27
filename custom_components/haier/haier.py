import hashlib
import json
import logging
import random
import time
from datetime import datetime
from urllib.parse import urlparse

import aiohttp

_LOGGER = logging.getLogger(__name__)

CLIENT_ID = 'upluszhushou'
CLIENT_SECRET = 'eZOQScs1pjXyzs'
APP_ID = 'MB-SYJCSGJYY-0000'
APP_KEY = '64ad7e690287d740f6ed00924264e3d9'
UHONE_CLIENT_ID = '956877020056553-08002700DC94'

TOKEN_API = 'https://account-api.haier.net/oauth/token'
GET_DEVICES_API = 'https://uws.haier.net/uds/v1/protected/deviceinfos'
GET_DEVICE_NET_QUALITY_API = 'https://uws.haier.net/uds/v1/protected/{}/deviceNetQuality'
GET_DEVICE_LAST_REPORT_STATUS_API = 'https://uws.haier.net/uds/v1/protected/{}/lastReportStatus'
SEND_COMMAND_API = 'https://uws.haier.net/stdudse/v1/sendbatchCmd/{}'
GET_HARDWARE_CONFIG_API = 'https://standardcfm.haigeek.com/hardwareconfig/file/getFuncModelJsonUrl?typeid={}&servicename=SDK&servicekey=1234567890abcdefghigklmnopqrstuv'


class HaierClientException(Exception):
    pass


class HaierClient:

    _token: str = None

    _token_created_at: datetime = None

    def __init__(self, username: str, password: str):
        self._username = username
        self._password = password

    async def try_login(self):
        data = {
            'client_id': 'upluszhushou',
            'client_secret': 'eZOQScs1pjXyzs',
            'grant_type': 'password',
            'connection': 'basic_password',
            'username': self._username,
            'password': self._password,
            'type_uhome': 'type_uhome_common_token',
            'uhome_client_id': UHONE_CLIENT_ID,
            'uhome_app_id': APP_ID,
            'uhome_sign': HaierClient._binary_to_hex_string(
                hashlib.sha256((APP_ID + APP_KEY + UHONE_CLIENT_ID).encode('utf-8')).digest()
            )
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url=TOKEN_API, data=data) as response:
                content = await response.json()

                if 'error' in content:
                    raise HaierClientException(content['error'])

                self._token = content['uhome_access_token']
                self._token_created_at = datetime.now()

    async def get_token(self):
        # 未登录或9天后自动重新登录
        if self._token is None or (datetime.now() - self._token_created_at).days >= 9:
            await self.try_login()

        return self._token

    async def get_devices(self):
        """
        获取设备列表
        """
        headers = await self._generate_common_headers(GET_DEVICES_API)
        async with aiohttp.ClientSession() as http_client:
            async with http_client.get(url=GET_DEVICES_API, headers=headers) as response:
                content = await response.json(content_type=None)
                self._assert_response_successful(content)

                return content['deviceinfos']

    async def get_net_quality_by_device(self, device_id: str):
        """
        获取设备网络质量
        """
        url = GET_DEVICE_NET_QUALITY_API.format(device_id)
        headers = await self._generate_common_headers(url)

        async with aiohttp.ClientSession() as http_client:
            async with http_client.get(url=url, headers=headers) as response:
                content = await response.json(content_type=None)
                self._assert_response_successful(content)

                return content['deviceNetQualityDto']

    async def get_last_report_status_by_device(self, device_id: str):
        """
        获取设备最新状态
        """
        url = GET_DEVICE_LAST_REPORT_STATUS_API.format(device_id)
        headers = await self._generate_common_headers(url)

        async with aiohttp.ClientSession() as http_client:
            async with http_client.get(url=url, headers=headers) as response:
                content = await response.json(content_type=None)
                self._assert_response_successful(content)

                return content['deviceStatus']['statuses']

    async def send_command(self, device_id: str, args: dict):
        url = SEND_COMMAND_API.format(device_id)

        sn = time.strftime('%Y%m%d%H%M%S') + str(random.randint(100000, 999999))
        payload = {
            'sn': sn,
            'cmdMsgList': [{
                'deviceId': device_id,
                'index': 0,
                'cmdArgs': args,
                'subSn': sn + ':0'
            }]
        }

        headers = await self._generate_common_headers(url, json.dumps(payload))

        async with aiohttp.ClientSession() as http_client:
            async with http_client.post(url=url, headers=headers, json=payload) as response:
                content = await response.json(content_type=None)
                self._assert_response_successful(content)

    async def get_hardware_config(self, wifi_type: str):
        url = GET_HARDWARE_CONFIG_API.format(wifi_type)

        async with aiohttp.ClientSession() as http_client:
            async with http_client.get(url=url) as response:
                content = await response.json(content_type=None)

                if 'data' not in content or 'url' not in content['data']:
                    _LOGGER.error('获取配置信息失败, wifi_type: {}, response: {}'.format(wifi_type, json.dumps(content)))
                    raise HaierClientException('获取配置文件失败')

                async with http_client.get(url=content['data']['url']) as config_resp:
                    return await config_resp.json(content_type=None)

    async def _generate_common_headers(self, api, body=''):
        timestamp = str(int(time.time() * 1000))
        # 报文流水(客户端唯一)客户端交易流水号。20位,
        # 前14位时间戳（格式：yyyyMMddHHmmss）,
        # 后6位流水号。交易发生时,根据交易 笔数自增量。App应用访问uws接口时必须确保每次请求唯一，不能重复。
        sequence_id = time.strftime('%Y%m%d%H%M%S') + str(random.randint(100000, 999999))

        return {
            'accessToken': await self.get_token(),
            'appId': APP_ID,
            'appKey': APP_KEY,
            'appVersion': '1.0',
            'clientId': UHONE_CLIENT_ID,
            'language': 'zh-cn',
            'sequenceId': sequence_id,
            'sign': self._sign(timestamp, body, api),
            'timestamp': timestamp,
            'timezone': '+8'
        }

    @staticmethod
    def _assert_response_successful(resp):
        if 'retCode' in resp and resp['retCode'] != '00000':
            raise HaierClientException(resp['retInfo'])

    @staticmethod
    def _binary_to_hex_string(bytes):
        ret = ''
        hex_str = '0123456789abcdef'
        for b in bytes:
            ret += hex_str[(b & 0xF0) >> 4]
            ret += hex_str[b & 0x0F]

        return ret

    @staticmethod
    def _sign(timestamp, body, url):
        content = urlparse(url).path \
                  + str(body).replace('\t', '').replace('\r', '').replace('\n', '').replace(' ', '') \
                  + str(APP_ID) \
                  + str(APP_KEY) \
                  + str(timestamp)

        return hashlib.sha256(content.encode('utf-8')).hexdigest()
