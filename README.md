# Haier

本插件可将海尔智家中的设备接入HomeAssistant，理论上支持所有设备。

> [!NOTE]
> 提交问题时请按Issues模版填写，未按模板填写问题会被忽略和关闭!!!

## 已支持实体
- Switch
- Number
- Select
- Sensor
- Binary Sensor
- Climate (Beta)

## 安装

方法1：下载并复制`custom_components/haier`文件夹到HomeAssistant根目录下的`custom_components`文件夹即可完成安装

方法2：已经安装了HACS，可以点击按钮快速安装 [![通过HACS添加集成](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=banto6&repository=haier&category=integration)

## 配置

配置 > 设备与服务 >  集成 >  添加集成 > 搜索`haier`

或者点击: [![添加集成](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start?domain=haier)

## 调试
在`configuration.yaml`中加入以下配置来打开调试日志。

```yaml
logger:
  default: warn
  logs:
    custom_components.haier: debug
```
