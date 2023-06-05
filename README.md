# Haier

本插件可将海尔智家中的设备接入HomeAssistant，理论上支持所有设备。

## 安装
下载并复制`custom_components/haier`文件夹到HomeAssistant根目录下的`custom_components`文件夹即可完成安装

## 配置

配置 > 设备与服务 >  集成 >  添加集成 > 搜索`haier`

## 已测试设备

#### 热水器
- JSQ30-16WN9S


## 调试
在`configuration.yaml`中加入以下配置来打开调试日志。

```yaml
logger:
  default: warn
  logs:
    custom_components.haier: debug
```