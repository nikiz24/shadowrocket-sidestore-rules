# Shadowrocket：分流、去广告和 MITM 模块，配合 SideStore 续签

本项目的续签通路只使用 **Shadowrocket**。完整配置包含：原生 `Include Route 10.7.0.1/32` 开关、SideStore 的有效配对文件，以及固定到 `10.7.0.1` 的实际设备连接地址。导入规则模块本身不会设置这三项。

[打开一键安装页](https://nikiz24.github.io/shadowrocket-sidestore-rules/)

或使用 iPhone 相机扫描二维码：

![安装到 Shadowrocket](docs/install.png)

## 使用

1. 在 Shadowrocket 中选择**本地 `default.conf`**，全局路由设为“配置”，选择自己的有效节点。
2. 扫上方二维码，或在 iPhone Safari 打开安装页，点击“一键导入到 Shadowrocket”，按提示安装并启用这一个模块。
3. 在 **Shadowrocket → 设置 → 其它 → Include Route 10.7.0.1/32** 开启原生回环。不同语言/版本可能显示为“包含路由 10.7.0.1/32”。断开并重连 VPN，连接 Wi-Fi。
4. 在新版内置 SideStore 中打开 **Settings → Connection Configuration**，保持 **Use Local VPN** 开启，在 **User Configuration** 区域把 **Device IP** 填为 `10.7.0.1`，**RemotePair Port** 留空，然后点 **Confirm** 并按提示重新打开。这里的 Use Local VPN 是“使用本机 VPN”的通用模式，适用于 Shadowrocket。
5. 若还没配过 MITM：在当前 `default.conf` 的 `ⓘ → HTTPS 解密 → 证书`生成、安装 CA；随后在 iOS 的“证书信任设置”中信任它，并确认 HTTPS 解密已开启。**续签本身不依赖 MITM；这是额外的 HTTPS 重写功能。**
6. 在 SideStore 中先手动 Refresh All，再断开重连 Shadowrocket、重开 LiveContainer 测试一次，确认实际连接地址没有被自动探测覆盖。成功后再设置每日快捷指令。

Shadowrocket 官方在 **2.2.91 (3386) 测试版**加入原生 `10.7.0.1/32` 回环；请使用包含此功能的新版。

## SideStore 版本与固定设备地址

LiveContainer 3.8.0 携带的旧 SideStore 0.6.4 会从 VPN 接口推算对端。此次实机日志显示它把 Shadowrocket 的 `198.18.0.1/24` 推算为 `198.18.0.2`，连接后报 `early eof`。即使 `10.7.0.1` 的原生回环已经开启，旧版依然可能连错地址。

旧版 **Health Check → VPN IP Configuration** 只展示探测结果，没有可编辑的 Device IP。应使用带有 **Connection Configuration → User Configuration → Device IP** 的构建。已核对官方 [Nightly 合并版](https://github.com/LiveContainer/LiveContainer/releases/tag/nightly) 的 LiveContainer **3.8.11** / SideStore **0.7.0-20261017.511+ee3cc16a** 包含这项功能；网络库对手动覆盖地址优先处理，并在重连时保留它。

该包为 Nightly 构建。升级应保持相同 Apple ID 和 Bundle ID，使用原位安装，并先备份容器数据。不要仅凭 Health Check 的 `DDI Not Mounted` 就认定必须重装 DDI：连接失败时，旧版会把读取 DDI 状态的异常显示成未挂载。

## 每日自动续签

在 iPhone“快捷指令”中新建“LiveContainer 自动续签”，依次添加：

```text
设置 VPN → 连接 Shadowrocket
等待 → 5 秒
LiveContainer → 刷新所有 App / Refresh All Apps
```

先手动运行并确认 SideStore 的到期时间更新，再为这个快捷指令添加“特定时间 → 每天 → 立即运行”自动化。合并版需使用 **LiveContainer** 提供的刷新动作。最后测试一次锁屏运行，并检查第二天的结果；创建自动化不代表每次后台执行都会成功。

这里每日执行的是 IPA 续签；下面的模块自动更新负责规则同步，两者分别配置。

如果之前导入过旧版多文件方案，切回本地 `default.conf`，停用旧增强模块与证书模块，再按上述步骤配置。其他已启用模块也可能影响最终规则和 MITM 主机名，排查时先停用有重叠功能的模块。

## 规则更新

GitHub Actions 每天北京时间 **08:30**左右同步原作者的完整规则；GitHub 调度可能延后。上游下载失败或结构异常时，保留现有版本。

手机端打开 `Shadowrocket → 设置 → 自动更新 → 模块`，设为每天更新，并允许 iOS 后台 App 刷新。也可以在模块列表手动更新本模块。后台调度由 iOS 决定。

**更新的是这个远程模块。`default.conf` 和其中的 CA 留在本地，因此本方案无需额外的证书模块。** 请不要把本地证书配置改成会被远程覆盖的配置。

模块直接地址，可填入“配置 → 模块 → ＋”：

```text
https://raw.githubusercontent.com/nikiz24/shadowrocket-sidestore-rules/main/Shadowrocket-SideStore.sgmodule
```

安装链接语法为 `shadowrocket://install?module=` 加 URL 编码后的上方地址。GitHub 的 Markdown 页面可能不允许直接打开自定义协议，安装页提供实际按钮，二维码也直接编码此安装链接。

## 功能

- 沿用 Johnshall `sr_cnip_ad.conf` 的全部分流和广告规则及其顺序。
- 增加 `10.7.0.1/32` DIRECT 规则。真正的本机回环由 Shadowrocket 的原生开关提供，须在手机上单独启用。
- 开启 MITM，限定于 `g.cn,*.g.cn,google.cn,*.google.cn`，配合原版 Google CN 跳转。其他 HTTPS 内容过滤需要对应服务的重写模块。
- 只发布公开规则，模块不含 CA 证书、私钥、Apple 账号、节点凭据。

“自签”由 SideStore / 相应签名工具完成。回环开关、有效 pairing、有效签名证书/登录状态是各自独立的条件，规则模块不能提供配对文件。DNS、IP 路由等通用参数使用本地基础配置；新版模块只发布 `[Rule]`、`[URL Rewrite]`、`[MITM]`。

## 提示 pairing file is invalid or missing

该错误优先检查配对文件。用 USB 连接并解锁这台 iPhone，在电脑 iloader 中确认设备，然后选择 **Manage Pairing File / 管理配对文件 → LiveContainer 这一行的 Place / 放置**。完全退出并重新打开 LiveContainer 后，在内置 SideStore 中重试。

对于合并版，iloader 写入的路径是 LiveContainer 的 `Documents/SideStore/Documents/ALTPairingFile.mobiledevicepairing`。如文件已经写入但仍提示无效，再按 SideStore 官方诊断流程重建这台设备的配对记录。不要公开或提交配对文件，它包含设备配对密钥。

## 提示 early eof、Unable to manage profiles 或 DDI Not Mounted

先检查实际连接目标。若日志出现 `setTunnelPeerIp(198.18.0.2)` 或相似的自动探测地址，按上文升级到支持手动覆盖的 SideStore，再固定 Device IP 为 `10.7.0.1`。规则模块无法改写 SideStore 应用内部的目标选择。

新版界面仍可能展示 **Auto Discovered from network** 的 `198.18.*` 地址；应重点查看 **User Configuration** 是否已保存 `10.7.0.1`，以及日志中的实际 device endpoint。若实际目标已经正确但仍失败，再检查回环开关、Wi-Fi、配对和开发者服务状态。

## 开发与验证

```sh
python3 -m unittest discover -s tests -v
python3 scripts/build.py
```

构建信息见 [build-info.json](build-info.json)。检查覆盖原规则顺序、原 URL 重写、模块不冒充原生隧道设置、拒绝异常上游、CA 数据不进入发布模块。手机端的模块编译、续签、MITM 与后台更新仍需在实际设备中验证。

## 来源与许可

- 原始规则：[Moshel / Johnshall](https://github.com/Johnshall/Shadowrocket-ADBlock-Rules-Forever/blob/release/sr_cnip_ad.conf)，CC BY-SA 4.0。
- 续签场景：[Luke 的博客](https://bssn520.github.io/p/22/)、[V2EX 讨论](https://v2ex.com/t/1253108)。
- 回环能力：[Shadowrocket 官方更新记录](https://t.me/s/ShadowrocketNews/1588)。
- 原生开关位置：[LoopCtrl 的实际使用说明](https://github.com/Souitou-iop/LoopCtrl#requirements)。
- 配对错误：[SideStore 官方诊断](https://docs.sidestore.io/docs/troubleshooting/error-codes)、[iloader 的合并版配对路径](https://github.com/nab138/iloader/blob/main/src-tauri/src/pairing.rs)。
- 固定设备地址：[官方合并版连接设置](https://github.com/LiveContainer/SideStore/blob/ee3cc16a/SideStore/Views/Settings/Advanced/Connection/ConnectionConfigView.swift)、[网络库的覆盖地址处理](https://github.com/SideStore/minimuxer/blob/12be70dc2627307a16bfd2dc7a009080d5bec909/Sources/Services/DeviceConnectionManager.swift)。
- 合并版快捷指令动作：[LiveContainer 官方自动续签说明](https://livecontainer.github.io/docs/installation/lc_sidestore#auto-refresh-shortcut)。
- 模块与安装协议：[Shadowrocket 社区手册](https://github.com/LOWERTOP/Shadowrocket/wiki)。

在上游规则上增加本机地址 DIRECT 规则与 MITM 设置，并以远程模块交付。修改日期：2026-11-02。派生配置和生成脚本按 CC BY-SA 4.0 提供，见 [LICENSE](LICENSE)。
