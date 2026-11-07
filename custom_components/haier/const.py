from homeassistant.const import Platform

DOMAIN = 'haier'

CONFIG_ENTRY_VERSION = 3

SUPPORTED_PLATFORMS = [
    Platform.SELECT,
    Platform.NUMBER,
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.SWITCH,
    Platform.CLIMATE,
    Platform.WATER_HEATER,
    Platform.COVER,
    Platform.BUTTON,
]

FILTER_TYPE_INCLUDE = 'include'
FILTER_TYPE_EXCLUDE = 'exclude'

# 海尔的接口按区域分主机，目前只接入中国大陆
DEFAULT_REGION = 'cn'
# 接口 Accept-Language 使用的中文标识
DEFAULT_LANGUAGE = 'zh-Hans'

# OAuth 配置
OAUTH2_AUTH_URL = 'https://account.haier.com/oauth/authorize'
# 海尔为这个 client_id 只注册了这一个回调值，且换 token 时会逐字符比对。
# 运行时用 haier.oauth2.get_redirect_uri() 按 HA 的 external_url/internal_url
# 推导，只有推导结果与本值一致时才允许走网页登录；本值同时作为推导失败时的兜底。
OAUTH2_CALLBACK_URL = 'http://homeassistant.local:8123/auth/external/callback'
# external callback 的相对路径，拼在 HA 对外地址之后
OAUTH2_CALLBACK_PATH = '/auth/external/callback'

# API 主机与端点
API_HOSTS_MAP = {
    DEFAULT_REGION: 'ha.haier.net',
}

API_ENDPOINT_MAP = {
    'token': '/api-gw/ha/se/account/token',
    'refresh_token': '/api-gw/ha/se/account/refresh/token',
    'account_info': '/api-gw/ha/se/account/info',
}

# 应用配置
APP_ID = 'MB-ISP72111109101-0004'
OAUTH2_CLIENT_ID = 'SV-ISP72111109101-0004'
APP_VERSION = '1.0.0'

# token 剩余有效期低于这个值时提前续期（1 天）
TOKEN_BUFFER_INTERVAL = 86400
