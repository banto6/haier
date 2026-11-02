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
- Climate

## 安装

方法1：下载并复制`custom_components/haier`文件夹到HomeAssistant根目录下的`custom_components`文件夹即可完成安装

方法2：已经安装了HACS，可以点击按钮快速安装 [![通过HACS添加集成](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=banto6&repository=haier&category=integration)

## 配置

配置 > 设备与服务 >  集成 >  添加集成 > 搜索`haier`

或者点击: [![添加集成](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start?domain=haier)


## 发送原始指令

通过 `haier.send_raw_command` 可向指定海尔设备发送原始控制指令。

- `device_id`：海尔侧的原始设备ID，可在对应设备信息的“序列号”中查看，填写时需保留大小写。
- `attrs`： 原始控制指令

以支持以下属性的热水器为例，将目标温度设为 42℃：

```yaml
action: haier.send_raw_command
data:
  device_id: AABBCCDDEEFF
  attrs:
    targetTemp: "42"
```

集成会将 `attrs` 原样提交给网关，不校验或转换其中的内容。调用成功仅表示控制事件已提交，不代表设备已执行指令。

## 常见问题

遇到问题提交issues前，请先查看[常见问题](https://github.com/banto6/haier/issues/186)中是否已存在。


## 调试
在`configuration.yaml`中加入以下配置来打开调试日志。

```yaml
logger:
  default: warn
  logs:
    custom_components.haier: debug
```
