import asyncio
import hashlib
import json
import logging
import random
import time
from functools import wraps
from typing import List, Dict
from urllib.parse import urlparse

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store

from .device import HaierDevice

_LOGGER = logging.getLogger(__name__)

APP_ID = 'MB-SHEZJAPPWXXCX-0000'
APP_KEY = '79ce99cc7f9804663939676031b8a427'

REFRESH_TOKEN_API = 'https://zj.haier.net/api-gw/oauthserver/account/v1/refreshToken'
GET_USER_INFO_API = 'https://account-api.haier.net/v2/haier/userinfo'
GET_DEVICES_API = 'https://uws.haier.net/uds/v1/protected/deviceinfos'
GET_WSS_GW_API = 'https://uws.haier.net/gmsWS/wsag/assign'
GET_DIGITAL_MODEL_API = 'https://uws.haier.net/shadow/v1/devdigitalmodels'

def retry_on_exception(exceptions, max_tries=3):
    """
    重试装饰器
    :param exceptions: 需要捕获并重试的异常（元组）
    :param max_tries: 最大尝试次数
    """

    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            last_exception = None
            attempt = 0

            while True:
                try:
                    return await func(*args, **kwargs)
                except exceptions as err:
                    if attempt < max_tries:
                        _LOGGER.warning(
                            "捕获到异常 %s。进行第 %s 次重试...",
                            type(err).__name__, attempt + 1
                        )

                    else:
                        last_exception = err
                        break
                finally:
                    attempt += 1

            _LOGGER.error("达到最大重试次数 (%s): %s", max_tries, last_exception)

            raise last_exception

        return wrapper

    return decorator


class TokenInfo:

    def __init__(self, token: str, refresh_token: str, expires_in: int):
        self._token = token
        self._refresh_token = refresh_token
        self._expires_in = expires_in

    @property
    def token(self) -> str:
        return self._token

    @property
    def refresh_token(self) -> str:
        return self._refresh_token

    @property
    def expires_in(self) -> int:
        return self._expires_in


class HaierClientException(Exception):
    pass


class HaierClient:

    def __init__(self, hass: HomeAssistant, client_id: str, token: str):
        self._client_id = client_id
        self._token = token
        self._hass = hass
        self._session = async_get_clientsession(hass)

    @retry_on_exception(exceptions=(aiohttp.ClientError, asyncio.TimeoutError))
    async def refresh_token(self, refresh_token: str) -> TokenInfo:
        """
        刷新token
        :return:
        """
        payload = {
            'refreshToken': refresh_token
        }

        headers = await self._generate_common_headers(REFRESH_TOKEN_API, json.dumps(payload))
        async with self._session.post(url=REFRESH_TOKEN_API, headers=headers, json=payload) as response:
            content = await response.json(content_type=None)
            self._assert_response_successful(content)

            token_info = content['data']['tokenInfo']
            return TokenInfo(
                token_info['accountToken'],
                token_info['refreshToken'],
                token_info['expiresIn']
            )

    @retry_on_exception(exceptions=(aiohttp.ClientError, asyncio.TimeoutError))
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

    @retry_on_exception(exceptions=(aiohttp.ClientError, asyncio.TimeoutError))
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

    @retry_on_exception(exceptions=(aiohttp.ClientError, asyncio.TimeoutError))
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

    async def get_digital_model_from_cache(self, device: HaierDevice) -> list:
        """
        尝试从缓存中获取设备attributes，若获取失败则自动从远程获取并保存到缓存中
        :param device:
        :return:
        """
        store = Store(self._hass, 1, 'haier/device_{}.json'.format(device.id))
        cache = None
        try:
            cache = await store.async_load()
            if isinstance(cache, str):
                raise RuntimeError('cache is invalid')
        except Exception:
            _LOGGER.warning("Device {} cache is invalid".format(device.id))
            await store.async_remove()
            cache = None

        if cache:
            _LOGGER.info("Device {} get digital model from cache successful".format(device.id))
            return cache['attributes']

        _LOGGER.info("Device {} get digital model from cache fail, attempt to obtain remotely".format(device.id))
        attributes = await self.get_digital_model(device.id)
        await store.async_save({
            'device': {
                'name': device.name,
                'type': device.type,
                'product_code': device.product_code,
                'product_name': device.product_name,
                'wifi_type': device.wifi_type
            },
            'attributes': attributes
        })

        return attributes

    @retry_on_exception(exceptions=(aiohttp.ClientError, asyncio.TimeoutError))
    async def get_device_snapshot_data(self, deviceId: str) -> dict:
        """
        获取指定设备最新的属性数据
        :param deviceId:
        :return:
        """
        values = {}

        attributes = await self.get_digital_model(deviceId)
        # 从attributes中读取实体值
        for attribute in attributes:
            if 'value' not in attribute:
                continue

            values[attribute['name']] = attribute['value']

        return values

    @retry_on_exception(exceptions=(aiohttp.ClientError, asyncio.TimeoutError))
    async def get_devices_online_status(self) -> Dict[str, bool]:
        """
        获取所有设备的在线状态
        :return:
        """
        headers = await self._generate_common_headers(GET_DEVICES_API)
        async with self._session.get(url=GET_DEVICES_API, headers=headers) as response:
            content = await response.json(content_type=None)
            self._assert_response_successful(content)

            devices = {}
            for device in content['deviceinfos']:
                devices[device['deviceId']] = device['online']

            return devices

    @retry_on_exception(exceptions=(aiohttp.ClientError, asyncio.TimeoutError))
    async def get_device_gateway(self) -> str:
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
