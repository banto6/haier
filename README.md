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

添加集成时提供三种登录方式，任选其一即可。

## 三种登录方式的区别

| 对比项 | 官方授权页登录（推荐） | 账号密码登录 | 手动填写 Token |
| --- | --- | --- | --- |
| 操作方式 | 跳转到海尔官方授权页，可选扫码、手机号验证码、账号密码 | 在 Home Assistant 表单中填手机号 + 密码 | 在 Home Assistant 表单中填 Client Id、Refresh Token 和 Token 来源 |
| 密码是否经过本插件 | 否，只填在海尔的页面上 | 是，但仅用于本次登录，不写入配置 | 否 |
| 是否需要 Home Assistant 对外可访问 | **需要**，浏览器要能回调到 `http://homeassistant.local:8123` | 不需要 | 不需要 |
| 是否需要 mDNS / external_url 配置 | **需要**，见下节 | 不需要 | 不需要 |
| clientId | 由插件生成，形如 `HA…….cn.……` | 手机号 | 用户自行填写 |
| Token 签发与续期 | `ha.haier.net` 的 OAuth2 端点 | zj 网关 | 由 Token 来源决定 |

三种方式的取舍：

1. **官方授权页登录**：在海尔官方页面完成登录，密码不经过插件，扫码即可接入，推荐优先使用。代价是它依赖一个写死的回调地址，安装环境（主机名、端口、是否经过反向代理）不合适时无法使用，需要按下一节做一次配置。
2. **账号密码登录**：不依赖回调地址，任何安装方式、任何访问地址都能用。代价是密码要填进 Home Assistant 的表单（只在本次登录使用，不保存），且账号需要支持密码登录。
3. **手动填写 Token**：给高级用户准备，自行提供 Client Id 和 Refresh Token，适合手上已有 Token、或要在不同环境之间迁移的场景。

> [!IMPORTANT]
> 海尔的网页授权和账号密码是两套账号体系：网页授权只拿得到 userId，账号密码登录只拿得到手机号，两者无法互相换算（`account/info` 只返回 `userId`/`nickName`）。
>
> 网页授权失效（token 过期且续期失败）时，集成条目上会出现「重新认证」入口，重新授权后账号、设备、实体和自动化都保留。要从账号密码登录换成官方授权页登录，走「配置」→「更新账户」→「改用官方授权页」也可以拉起同一个流程。

## 网页授权登录：mDNS 与访问地址要求

官方授权页登录对访问地址有硬性要求，不同安装方式需要做的事不一样。先按自己的安装方式对号入座，具体原因和操作见后文。

### 不同安装方式是否需要配置 mDNS

| 安装方式 | 是否已经广播 `homeassistant.local` | 需要做什么 |
| --- | --- | --- |
| Home Assistant OS（裸机安装 / 官方镜像虚拟机） | 是。系统自带 avahi-daemon，默认主机名就是 `homeassistant` | 无需额外配置，`external_url` 保持默认即可 |
| Home Assistant Supervised（Debian 宿主机） | 通常否。广播的是宿主机的机名（如 `debian.local`） | 在宿主机上补一条 `homeassistant.local` 的别名记录 |
| Home Assistant Container（Docker） | 否 | 在宿主机上安装 avahi-daemon 并发布别名，容器建议使用 host 网络 |
| Home Assistant Core（Python venv） | 视宿主机而定（有没有装 avahi-daemon、主机名是否叫 `homeassistant`） | 同 Supervised，按下面步骤确认并补上 |

几个容易踩的点：

- **在容器里改 `hostname` 没用**。Home Assistant 的 zeroconf 广播用的是实例 uuid（形如 `<32位十六进制>.local`），不是容器 hostname，改完依然解析不到 `homeassistant.local`。
- **虚拟机请用桥接网络**。NAT 模式下虚拟机之外的浏览器访问不到虚拟机的 8123，网页授权即使地址匹配也会卡在回调那一步。
- 「主机名就是 `homeassistant`」只有 Home Assistant OS 才有这个前提。在 OS 里改过主机名后，`homeassistant.local` 会跟着变成 `<新机名>.local`，此时要么改回 `homeassistant`，要么用账号密码登录。

### 为什么需要额外配置

海尔只为网页授权注册了一个固定的回调地址 `http://homeassistant.local:8123/auth/external/callback`，并且在用 `code` 换 `access_token` 时会对 `redirectUri` 做逐字符比对——协议、主机名、端口、路径任一不同，都会在最后一步被判为 `invalid_grant: Invalid redirect`。这个白名单在服务端，插件无法修改。

所以走官方授权页登录时，要同时满足三条：

1. Home Assistant 的对外地址是 `http://homeassistant.local:8123`（即 `external_url`；未配置时用 `internal_url`）；
2. `homeassistant.local` 能解析到这台 Home Assistant 所在主机的 IP；
3. 发起授权的浏览器（电脑或手机）能直接访问该 IP 的 8123 端口。

插件在跳转授权页之前会先按当前地址推导一次回调地址，不匹配就直接中止，不会让用户白跑一趟授权页：

> 网页登录不可用：海尔只接受回调地址 http://homeassistant.local:8123/auth/external/callback，而根据当前 Home Assistant 的访问地址推导出的回调是 ……。请把「设置 → 系统 → 网络」中的 external_url 配置为与之匹配的地址后重试，或改用「账号密码登录」。

### external_url 怎么配

「设置 → 系统 → 网络 → 外部 URL」填 `http://homeassistant.local:8123`。

用 `configuration.yaml` 时注意写在 `homeassistant:` 块下面，写在根级不生效：

```yaml
homeassistant:
  external_url: "http://homeassistant.local:8123"
  internal_url: "http://192.168.1.10:8123"
```

以下情况网页授权一定不可用，请直接改用账号密码登录：

- 通过 HTTPS 或反向代理访问（`https://`，或用了 8123 以外的端口）；
- 暴露到公网、用域名或公网 IP 访问；
- `external_url` 带了路径（如 `/lovelace`）或多余的末尾斜杠。

### 在 Linux 宿主机上发布 homeassistant.local

以 Debian / Ubuntu 宿主机为例（Supervised、Container、Core 都适用），把 `192.168.1.10` 换成宿主机实际 IP。

**第一步：安装并启动 avahi**

```bash
sudo apt update
sudo apt install -y avahi-daemon avahi-utils
sudo systemctl enable --now avahi-daemon
```

**第二步：新建 `/etc/systemd/system/haier-mdns.service`**

```ini
[Unit]
Description=Publish homeassistant.local via mDNS (Haier OAuth callback)
After=avahi-daemon.service
Requires=avahi-daemon.service

[Service]
Type=simple
ExecStart=/usr/bin/avahi-publish -a -R homeassistant.local 192.168.1.10
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

**第三步：启用服务**

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now haier-mdns
```

另一种写法是把记录直接写进 `/etc/avahi/hosts`，然后重启 avahi-daemon：

```text
192.168.1.10 homeassistant.local
```

```bash
sudo systemctl restart avahi-daemon
```

`/etc/avahi/hosts` 和上面的 `avahi-publish` 服务**只能用其中一种**，同时启用会互相争抢同名记录，avahi 日志里出现 `Local name collision`，别名反而不稳定。

### 验证

先在宿主机上确认记录已发布：

```bash
avahi-resolve -n homeassistant.local
# 期望输出：homeassistant.local	192.168.1.10
```

再在准备用来授权的电脑或手机上确认能解析、能访问：

```bash
ping homeassistant.local
```

浏览器打开 `http://homeassistant.local:8123` 能看到 Home Assistant 登录页，就可以回去添加集成了。

### 排查

| 现象 | 原因与处理 |
| --- | --- |
| 集成提示「网页登录不可用：海尔只接受回调地址 ……」 | `external_url` 与注册值不一致，按上文改；或直接用账号密码登录 |
| 授权页登录成功后仍报 `invalid_grant: Invalid redirect` | 实际发出的 `redirectUri` 与注册值不同：检查协议（必须 http）、端口（必须 8123）、末尾斜杠，以及是否被反向代理改写了地址 |
| `avahi-resolve` 没有任何输出 | avahi-daemon 没运行、主机不在同一广播域，或路由器禁止组播 / 开了 AP 隔离 |
| avahi 日志出现 `Local name collision` | `/etc/avahi/hosts` 与 `avahi-publish` 同时在发布同名记录，只保留一个 |
| 电脑能访问、手机不能 | 两台设备不在同一子网或被 AP 隔离；部分 Android 浏览器不解析 `.local` 域名，改用电脑 / iPhone 授权 |
| 不想动 mDNS | 在浏览器所在电脑的 hosts 文件里加一行 `192.168.1.10 homeassistant.local`（仅对该电脑生效），或改用账号密码登录 |

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
