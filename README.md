# AndroidCoolNet（Windows / ADB v0.4.0）

双击 `install.cmd`，自动检测 Android 版本/CPU 架构，补装缺失的 Google 基础组件，再安装官方 Clash Meta for Android、导入节点并设置应用白名单。无需 root，也无需在电脑预装 Python。手机需要开启 USB 调试、允许电脑连接，整个配置过程保持解锁，勿手动操作界面。

## 下载哪个包

从 [v0.4.0 发布页](https://github.com/gelinzhankai/AndroidCoolNet/releases/tag/v0.4.0) 下载附件（不要下载 GitHub 自动生成的 Source code 代替运行包）：

| 文件 | 用途 |
|---|---|
| `AndroidCoolNet-Windows-v0.4.0.zip`，约 63 MiB | 必选的手机基础包：Windows 便携运行环境、ADB、CMFA ARM64、脚本和模板；不含 Google APK |
| `AndroidCoolNet-Google-Offline-v0.4.0.zip`，约 181 MiB | 可选的 Google 离线组件包；含 Android 15/16/17 所需的不同 GSF 及共用 ARM Play 服务、商店 |
| `gsf-35.apk.zip` / `gsf-36.apk.zip` / `gsf-37.apk.zip` / `gms-arm64.apk.zip` / `play-store.apk.zip` | 自动下载使用的单组件附件；也可手动下载需要的几个 |
| `SHA256SUMS.txt` | 发布附件校验值 |

**已有完整 Google 组件时只需基础包，不会下载 Google APK。** 不含模拟器、系统镜像、AVD、Intel 专用 APK 或测试探针。无需按 Android 版本下载三个重复的大包；离线包由工具自动选用。基础包内置 CMFA ARM64，ARMv7 CMFA 如需安装会从上游下载；Google 离线组件包含 ARM64/ARMv7。Intel 设备缺失 Play 服务时没有可补装的清单项，会明确报告，不能使用 ARM 包代替。

## Google 组件获取步骤

1. 先显示设备 Android 版本、API、ABI，并列出 Google 服务框架、Google Play 服务、Play 商店的检测结果及缺失项。已有组件保留，禁用状态也保留；系统已有但当前用户卸载的组件直接恢复，无需下载。
2. 确有缺失且缓存不齐时，选择 **`1` 自动下载 / `2` 手动下载**。直接回车跳过本次 Google 补装，之后仍可继续 Clash 配置。所需文件都已缓存且 SHA-256 正确时不再询问下载。
3. 选择 `1`：电脑从固定版本 GitHub Release 按需下载单组件，显示百分比、已下载/总大小、速度；检查 ZIP 和 APK 的 SHA-256。不会整包下载所有 Android 版本。失败会转到手动方式，保留已通过校验的缓存。
4. 选择 `2` 或自动失败：**按回车打开仓库发布页**；下载离线包或所需单组件，然后回到命令行粘贴路径。输入 `0` 可跳过打开页面和补装。
5. 可以输入**一个 ZIP（无需解压）**、**一个文件夹**，或**多个 APK/ZIP 路径，以分号隔开**。路径支持空格及外层引号。不用按组件顺序，工具按文件哈希匹配；缺少的可以下一轮再输入，输错路径或校验不通过会提示重试。直接回车停止补装。

例如：

```text
D:\Downloads\AndroidCoolNet-Google-Offline-v0.4.0.zip
"D:\Downloads\Google 组件"
"D:\Downloads\gsf-35.apk.zip";"D:\Downloads\gms-arm64.apk.zip";"D:\Downloads\play-store.apk.zip"
```

推荐直接输入离线 ZIP 路径，最省操作。工具只提取本次缺失且匹配的 APK 到 `cache/gms/`，不会安装 ZIP 中的所有版本。手动提供其他版本/修改过的 APK 会被拒绝；需更新版本时由维护者先验签并更新固定清单。**所有本次所需文件校验完成后才开始安装**，下载/导入中断不会导致提前安装一半；Android 安装阶段若失败，前面已成功安装的组件会保留，下次只补缺失项。

## 使用

1. 解压手机基础包到一个可写目录，不要直接在压缩包中运行。Windows 10/11 x64；Google 缺失包匹配范围为 Android 15、16、17 正式版（API 35/36/37），主用户。Clash 流程仍接受 Android 7 以上，可用 `--skip-gms` 跳过补装。界面使用简体中文或英语。部分厂商还需开启「USB 调试（安全设置）」以允许模拟点击。
2. 只连接一台手机；多设备请运行 `install.cmd --serial 设备序列号`。首次在手机确认 USB 调试授权。已有 Clash 请先停止运行。
3. 双击 `install.cmd`，按提示粘贴 Clash/Mihomo **HTTPS** 订阅地址，**明文显示，按回车提交；直接留空回车跳过**。地址无效、下载失败或节点 YAML 解析失败时也会跳过，不中断客户端安装及白名单配置。支持包含 `proxies` 节点列表的 YAML；暂不支持仅含 `proxy-providers` 的配置、Base64 链接列表或订阅管理网页。
4. 等待界面自动配置，几十个系统应用可能需要十几分钟。有可用配置后在 Clash 首页点击启动，并自行确认首次 Android VPN 授权。跳过订阅时不创建或切换配置；已有配置保留，无配置时可稍后在手机导入。需要切换节点时进入 Clash 的代理页面选择。

订阅留空、下载失败或解析失败时，工具最后会再次说明原因，并提示手动导入可用节点、在「设置 > 覆写」检查规则模式及 DNS：IPv6 禁用、DNS 强制启用、DNS IPv6 禁用、Fake-IP、Name Server 列表设为 `8.8.8.8`。这些是手动操作提示，不表示工具已经改过覆写；有效订阅路径仍使用 `config/profile.yaml` 的参数。没有可用节点时，单独设置 DNS 并不能让应用获得代理网络。

**以后新安装的应用，需要自行进入「Clash 设置 > 网络 > 允许访问列表」勾选。** 必要时显示系统应用；若运行中的 VPN 未更新，停止并重新启动 Clash。

当前版本没有用 ADB shell 的 ping/curl 自动判定 ChatGPT/Google/Claude 是否可用。应用白名单按应用身份决定 VPN 路由，shell/root 的请求不代表目标应用；不能据此自动覆盖已有网络配置。已有网络可用、只想检查 Google 组件时使用 `install.cmd --detect-only`，不会安装/恢复 Google 组件或修改 Clash。`--gms-only` 则会补装缺失组件，二者含义不同。

仅检测：`install.cmd --detect-only`。本地 YAML：`install.cmd --profile-file C:\path\config.yaml`。如电脑下载失败可使用 `install.cmd --pc-download-proxy http://127.0.0.1:10808`；此参数只供电脑下载，不设置手机或模拟器代理。源代码版本可运行 `powershell -NoProfile -ExecutionPolicy Bypass -File Prepare.ps1` 准备 Python，再自行放置官方 platform-tools；便携包已经包含运行环境和 ADB。

## 白名单与分流

- 从主用户的全部已安装包中查找，**包名只要包含 `google` 就纳入候选，不区分大小写，包含系统应用**。另加包名不含 google 的 Play 商店 `com.android.vending`。
- `config/apps.json` 是可编辑模板，覆盖 ChatGPT、Claude、Grok、Gemini、Perplexity、Instagram、X、Telegram、Discord、Reddit、Facebook、WhatsApp、TikTok、YouTube、Netflix、Spotify、Disney+ 等。只勾选设备实际安装的包，不安装这些应用。
- Clash 自身只显示具备 INTERNET 权限或系统 UID 的应用。资源覆盖包等无网络权限组件无法勾选，工具把它们保留在报告的候选与排除列表中。共享 UID 的应用可能共享 VPN 访问资格，这是 Android 的限制。
- 模式是「仅允许已选择的应用」：白名单外的应用不进入 Clash VPN。白名单内再按 `config/rules.json` 匹配：私有地址、`.cn` 和列出的常见国内域名直连，其余走 PROXY。这里没有完整的中国 IP/域名库。
- 配置只采用订阅中的节点，不继承订阅的代理组、远程规则、控制器或分流设置。默认选第一个节点，不保证它可用；不会在代理失败时自动改为直连。
- 每次运行会重新设置 Clash 的应用白名单；提供有效订阅时才生成并选择节点配置，跳过订阅则保留原配置选择。保留其他配置；相同内容尽量复用同名配置。节点保存在手机 Clash 私有配置内，电脑只在内存中处理订阅；输入的 URL 会显示在当前终端，不写入工具报告。
- 第一版为本地配置快照，**没有订阅自动更新**。更新节点或安装新应用后重新运行。依赖 `dialer-proxy` 的链式节点暂不支持。

## 端口、IPv6、DNS 与手机“覆写”页

编辑 `config/profile.yaml`，然后提供有效订阅重新运行，即可把修改写入新生成的本地节点配置。也可用 `--profile-settings C:\path\profile.yaml` 指定其他模板。**跳过订阅时不会应用模板，也不会修改已有节点配置或手机的全局覆写。**

| 手机界面项 | YAML 字段 |
|---|---|
| HTTP Port | `port` |
| Socks Port | `socks-port` |
| Redirect Port | `redir-port` |
| TProxy Port | `tproxy-port` |
| Mixed Port | `mixed-port` |
| Authentication | `authentication`，如 `["user:password"]` |
| Allow LAN | `allow-lan` |
| IPv6 | `ipv6` |
| Bind Address | `bind-address` |
| External Controller | 必须在手机覆写页设置，不能通过此模板启用 |

模板中的 `null` 表示不输出该字段，不会清除手机上的覆写；端口 `0` 表示关闭对应监听。Redirect/TProxy 端口不等于 Android VPN 开关，应用白名单仍由手机的网络设置管理。其余可编辑字段包括 `mode`、`log-level` 和 `dns`。

手机“覆写”页有自己独立的私有配置文件。按已验证版本源码，主用户通常位于 `/data/user/0/com.github.metacubex.clash.meta/files/clash/override.json`，普通未 root 的 ADB 无法直接读写。此工具通过正常配置导入工作，不写该私有文件。

“Do not modify”表示不在此层覆盖，沿用导入配置，所以填写 YAML 后页面仍可能显示 Do not modify。截图中 IPv6 为 Disabled，意味着它会覆盖配置中的 `ipv6: true`；要沿用 YAML，需把手机这一项改回 Do not modify，或直接在页面改为 Enabled。常规顺序为导入配置 → 持久覆写 → 会话覆写，客户端还会对特定字段再作处理；例如 External Controller 会从导入配置中清除，只接受覆写页设置。

依据：[覆写存储实现](https://github.com/MetaCubeX/ClashMetaForAndroid/blob/v2.11.35/core/src/main/golang/native/config/override.go)、[覆写顺序及控制器处理](https://github.com/MetaCubeX/ClashMetaForAndroid/blob/v2.11.35/core/src/main/golang/native/config/process.go)。

## Google 缺失组件补装

默认先补装，再刷新包列表生成 Google 应用白名单。只补这三个基础组件：Google Services Framework、Google Play 服务、Google Play 商店；不捆绑老版本 Google Account Manager、同步组件或其他 Google 应用。

| 检测状态 | 行为 |
|---|---|
| 已安装，任意版本 | 跳过，保留 APK、数据和设置 |
| 已安装但被禁用 | 保留禁用状态，报告需要自行处理；不覆盖、不自动启用 |
| 系统已保留 APK，当前用户卸载 | 使用 `install-existing --user 0` 恢复已有版本 |
| 确实缺失 | 匹配系统版本和 ABI，检查固定 SHA-256，再用 `adb install --no-streaming -R --user 0` 安装 |

`-R` 明确禁止替换已有应用；每次操作前再检查一次包状态。先校验本次需要的全部 APK 和必要系统库，预检失败不开始补装。安装途中失败会停止后续 Google 组件、记录原因，继续 Clash 流程。Google 未齐全或被禁用时退出码为 2；这不表示 Google 登录成功。

Google 离线组件包包含 5 个已核验 APK（基础包不含这些文件）：

| 组件 | 固定版本 | 匹配范围 |
|---|---|---|
| GSF | 15 / 16 / 17，各自独立 APK | 分别仅 API 35 / 36 / 37，noarch |
| Play 服务 | 26.40.32，ARM 包 | API 35–37；arm64-v8a/armeabi-v7a |
| Play 商店 | 53.4.35-34，通用 APK | API 35–37；本工具手机补装面向 ARM |

APK 来自 APKMirror 的 Google LLC 页面，不是 Google 官方独立安装包下载渠道。发布前用 Android SDK `apksig` 核验 APK 签名及证书轮换链，链包含 Google 证书 SHA-256 `f0fd6c5b410f25cb25c3b53346c8972fae30f8ee7411df910480ad6b2d60db83`；核对包名、minSdk、targetSdk、ABI、必需系统库及无强制拆分依赖，运行时校验固定文件哈希。原始页面、版本、证书链、哈希见 `config/gms-packages.json`；文件在 `cache/gms/`。此清单供维护者更新审核后的包，不要仅改哈希来接受未知 APK。

仅补 Google：`install.cmd --gms-only`；只检测、不安装：`install.cmd --detect-only`；只做 Clash：`install.cmd --skip-gms`。多设备均可加 `--serial`。Google 阶段会单独保存报告，即使后续订阅/UI 中断也可查看。

**版本/架构匹配和安装成功不等于完整 GMS 可用。** 本工具不改系统分区、不授予 ROM 特权、不替换已有包、不绕过厂商安装限制或设备认证。有些 ROM 即使 APK 装齐，仍缺少系统权限/厂商支持，可能不能登录或正常推送。16/17 与 ARM 仅完成 APK 元数据、签名和选择逻辑验证；还没有对应实机验收。官方说明：[设备认证要求](https://www.android.com/certified/)、[检查 Play Protect 认证状态](https://support.google.com/googleplay/answer/7165974)。

## Clash 兼容边界

固定验证客户端为 CMFA `2.11.35.Meta`。已有不同版本时停止，不覆盖；已有同版本时复用。UI 自动化目前只适配此版本的英语/简体中文布局，厂商限制、字体缩放、弹窗或手动操作可能中断。中断时已有安装/白名单操作可能已经生效，处理提示后可重跑。

## 文件与隐私

- `install.cmd`：双击入口；`setup_tool.py`：配置与安装；`gms_assets.py`：下载和离线导入；`config/`：可编辑模板。
- `runtime/`：便携 Python 3.12.10 + PyYAML 6.0.3；`platform-tools/`：Google ADB 37.0.1。
- `cache/`：基础包只预置官方 CMFA ARM64 APK；其他 CMFA ABI 首次从上游发布页下载并校验固定 SHA-256。`cache/gms/` 是下载或手动导入后建立的 Google APK 缓存，首次运行可以不存在。
- `reports/`：设备信息、Google 补装结果、包名和选择结果，不包含订阅地址或节点密码。Google 阶段失败也会记录。分享报告前留意设备序列号。
- 导入使用仅监听本机回环地址的临时文件服务和 ADB reverse，结束后关闭并删除该映射；它不转发外网。
- `tests/`：开发测试，不需要在真实手机运行；其中节点只连接本地固定响应服务，不是可用的外网节点。

## 模拟器测试的网络隔离

本机电脑有 TUN 接口，清空 Android HTTP 代理不足以证明模拟器直连。因此本项目测试时使用飞行模式、关闭 Wi-Fi，核对默认网络为 `none`，仅通过 ADB 连接本地固定响应端点，端点不访问外网。没有借用电脑 10808/10810 代理，也没有关闭或修改电脑的代理设置。

这可以验证安装、配置、白名单及本地分流行为，不能证明真实节点、Google 登录、流媒体解锁或厂商 ROM 兼容性。详情见 `TESTING.md`。

## 上游来源

- [Clash Meta for Android v2.11.35](https://github.com/MetaCubeX/ClashMetaForAndroid/releases/tag/v2.11.35)，实现核对同名 tag；GPL-3.0，源码及许可证见该仓库。
- [Android SDK Platform-Tools](https://developer.android.com/tools/releases/platform-tools)，保留其 `NOTICE.txt`。
- [Python 3.12.10](https://www.python.org/downloads/release/python-31210/)，保留 runtime 内许可证。
- [PyYAML 6.0.3](https://pypi.org/project/PyYAML/6.0.3/)，保留 wheel 内许可证。
- [Mihomo 配置说明](https://wiki.metacubex.one/en/config/)。
