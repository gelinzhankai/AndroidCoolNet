# 测试记录

环境：Windows x64、Google 官方 Android 15 / API 35 / x86_64 模拟器 `Codex_API35_Play`，设备 `emulator-5580`。测试日期：2026-10-19。

## v0.4.0 拆包与按需下载

- 42 项自动化测试通过。新增 13 项覆盖：下载进度、HTTPS/大小/SHA-256 检查、自动失败转手动并保留已完成缓存、ZIP/文件夹/多个分号路径、中文空格引号、乱序与重命名 APK、损坏/错误哈希、ZIP 路径穿越保护、手动重试累积、跳过与输入结束。既有订阅、白名单和 Google 不覆盖逻辑回归通过。
- 清单移除 Intel Play 服务，仅保留 GSF 35/36/37、ARM Play 服务和通用商店五个 APK。API 35/36/37 × ARM64/ARMv7 选择通过，Intel 缺失 Play 服务会拒绝错误匹配。旧版六包验证记录为历史记录。
- 手机基础包不含 Google APK、Intel 专用客户端 APK、模拟器/系统镜像或测试文件。离线组件包包含五个 APK，单组件 ZIP 供自动下载。打包生成固定组件 URL、压缩文件 SHA-256/大小与 APK SHA-256/大小，校验缓存后再复用。
- 本轮实际模拟器验证：以一次性探针替代目标包，通过生产函数的手动 ZIP 获取 → 哈希识别 → ADB 缺失安装流程；再运行跳过；禁用状态保留；实际 `-R` 重装请求返回 `INSTALL_FAILED_ALREADY_EXISTS`。探针清理成功。三个预装 Google 包前后版本与 lastUpdateTime 一致。
- 模拟器全程飞行模式、Wi-Fi 关闭、无全局 HTTP 代理、默认网络 none。所有 ADB 测试显式限定 `emulator-5580`，没有改动真实手机。电脑侧 GitHub 下载与上传使用主机网络，不是模拟器网络。

复现：`runtime\python.exe -X utf8 -m unittest discover -s tests -v`；`package_release.py` 生成拆分包；`tests/smoke_release_v04.py` 校验全部附件哈希及离线 APK，并使用解压出来的便携 Python/ADB 在指定离线模拟器上执行只读检测和全组件已安装分支。打包不包含开发测试；源仓库提供这些脚本。

从零安装真实 Google 组件、ARM 手机上的实际运行、Android 16/17、厂商 ROM 权限/认证与 Google 登录仍未验收。用一次性测试包验证生产安装流程，不代表这些设备已兼容。未重跑未改动的 Clash 长时间 UI/本地分流测试。

## v0.3.1 结束提示

新增订阅留空/下载失败/解析失败/本地文件不可读的结束原因提示、手动覆写配置说明，以及新装应用需加入「设置 > 网络 > 允许访问列表」的提醒。已有 8 项订阅流程回归通过。此变更只涉及提示和文档，没有在已连接手机执行写入、安装、网络请求或界面点击，也没有增加基于 shell 的自动网络判定。

## v0.3 Google 补装验证

- 29 项自动化测试通过（新增 14 项）。覆盖 API 35/36/37 × ARM64/ARMv7/x86_64/x86 选包、拒绝未知 SDK/架构/预览版、已有组件跳过、禁用状态保留、系统已存在但用户卸载时恢复、仅安装缺失项、安装顺序、校验失败前不做变更、系统库缺失、检测后竞态、系统拒绝安装和安装后复查失败。
- 六个真实 APK 均经 SDK `apksig` 验签和证书轮换链验证；证书锚点与从官方 API35 Google Play 镜像提取的 GSF 一致。`aapt` 核验包名、minSdk、targetSdk、ABI 和系统库；无强制拆分依赖。`config/gms-packages.json` 记录元数据和 SHA-256。
- 实际模拟器运行 `--gms-only`，三个预装 Google 组件全部跳过。前后版本号、版本名、lastUpdateTime 一致。
- 同一生产安装函数搭配一次性测试包，实际验证缺失安装、重复运行跳过、禁用状态保留；另实际提交 `-R` 安装请求，Android 返回 `INSTALL_FAILED_ALREADY_EXISTS`。测试后删除探针。证据：`tests/artifacts/google-acceptance.json`。
- 网络始终保持 airplane_mode_on=1、wifi_on=0、http_proxy=null、默认网络 none；未使用电脑代理联网。下载 APK 是电脑侧操作。

本次没有拆除模拟器预装 GMS，没有改动已连接的真实手机，也没有重复未改动的长时间 Clash UI/流量测试。**真正无 GMS 的厂商 ROM 从零补装、Google 登录、设备认证，以及 Android 16/17 和 ARM 的实际运行均未验证。** 自动化模拟中的恢复路径不等于真实 ROM 已验收。

复现：`runtime\python.exe -X utf8 -m unittest discover -s tests -v`；仅在指定离线模拟器运行 `runtime\python.exe -X utf8 tests\verify_google_emulator.py`。重新生成安装包清单需要本机 SDK/JDK 和所有 APK：`runtime\python.exe -X utf8 tests\build_gms_catalog.py`。

## v0.2 增量验证

15 项自动化测试通过（原 7 项 + 新增 8 项）。新增测试覆盖明文 input 提示、空输入、下载失败、畸形 URL、无效订阅/本地 YAML 时继续安装及白名单流程，并确认不调用配置导入、不启动临时传输服务、不报告“配置已导入”。有效订阅仍导入，报告不包含输入链接。另验证可编辑 profile.yaml 的字段进入生成配置、null 省略及错误字段拒绝。

这些入口流程测试使用模拟 ADB/UI，未连接或改动真实手机，本次没有重跑未改动的模拟器 UI 勾选流程。默认配置生成结果 SHA-256 前缀仍为 `33d54bc9ba`，与下述已通过本地流量验证的默认测试配置完全一致。以下模拟器记录来自 v0.1 的实际测试。

## 网络边界

测试期间飞机模式为 1、Wi-Fi 为 0，Android 全局 HTTP 代理为 null，启动 VPN 前默认网络为 none。电脑存在 TUN，因此没有把“未设置 HTTP 代理”误当作绕过电脑代理的证据。模拟器没有外网连接，只经 ADB reverse 接入两个不转发外网的固定响应服务。

开发机下载官方 APK 使用电脑自己的网络；这与模拟器测试流量隔离。没有使用用户订阅、账号或节点凭据。

## 已完成的检查

- 官方 CMFA 2.11.35 x86_64 APK 校验 SHA-256 后通过 ADB 安装；便携包另含经过同样校验的官方 ARM64 APK。
- 主用户、Android API、ABI、Play 服务、GSF、Play 商店检测；三项 Google 组件已安装。
- 便携 Python + PyYAML 可运行；7 项单元测试通过，包括 Google 包名动态匹配、共享 UID 与更新系统包处理、无网络权限包识别、错误订阅拒绝、节点凭据无损解析、禁用订阅原分流/控制器配置继承。
- 便携 ZIP 完成 CRC 检查，解压至独立测试目录后，用其中的 Python 和 ADB 成功运行 `--detect-only`。
- 英语界面自动启用 VPN 路由、仅允许所选应用、显示系统应用并逐项勾选。简体中文选择器已对照该版本上游翻译，尚未做中文设备上的完整 UI 回归。
- 使用最终导入流程成功完成：临时 URL 读取、复制为本地 File、填写并校验名称、删除临时 URL 配置、激活新配置。再运行时复用同名配置成功。

本地验收通过：

| 检查 | 结果 |
|---|---|
| 应用候选 | 85 个（含 Google 包名测试探针）；38 个无网络权限资源/组件被排除 |
| VPN 实际 UID 覆盖 | 47 个选中包全部落在系统 VPN 的 UID 范围内；非白名单探针在范围外 |
| PROXY 规则 | 返回 `ANDROID_SETUP_TEST_PROXY` |
| 私有地址 DIRECT 规则 | 返回 `ANDROID_SETUP_TEST_DIRECT` |
| Google 包名探针（禁用 Java HTTP 代理） | 经 VPN 收到 `ANDROID_SETUP_TEST_PROXY` |
| 非白名单探针 | 返回 `PROBE_BLOCKED_NO_NETWORK`，没有进入 VPN |
| 清理 | 测试脚本关闭 VPN、删除自己的 ADB forward/reverse；默认网络恢复为 none |

源目录证据在 `tests/artifacts/acceptance.json`、`configuration.json` 和两张探针截图中。排除测试探针后，普通环境是 84 个候选、46 个可选包及 38 个无网络权限包。共享 UID 的权限信息和旧系统包副本均已纳入回归处理，Play 服务和 GSF 的 UID 已在 VPN 范围内确认。

这是最终模块组合的界面与本地流量验收，完整入口的首次长时间白名单扫描在开发中分段补测完成；未在另一台干净设备上重新做整包首次运行。没有验证真实节点访问、账号登录、ARM APK 实际运行、中文完整 UI、厂商 ROM 或物理 USB 兼容性。

## 复现

生产路径：`install.cmd --serial emulator-5580 --profile-file tests\fixture.yaml`。先阅读共享模拟器的 `H:\Android-Emulator\README.md`，确认没有其他对话使用，再启动；先设飞行模式并核对默认网络为 none。不要恢复磁盘基线、清空数据或改变电脑代理来复现普通测试。

开发测试脚本不随便携包分发，在源目录：

```powershell
& .\runtime\python.exe -X utf8 -m unittest discover -s tests -v
# 探针构建需要 Android SDK 35/build-tools 35.0.0 和 JDK 21：
& .\tests\Build-Probes.ps1
& .\platform-tools\adb.exe -s emulator-5580 install --user 0 .\tests\artifacts\probe-build\allowed.apk
& .\platform-tools\adb.exe -s emulator-5580 install --user 0 .\tests\artifacts\probe-build\excluded.apk
& .\runtime\python.exe -X utf8 .\setup_tool.py --serial emulator-5580 --profile-file .\tests\fixture.yaml
& .\runtime\python.exe -X utf8 .\tests\verify_emulator.py
```

探针只访问保留测试地址 `198.51.100.1`，并显式禁用 Java HTTP 代理以检验 VPN 捕获；不访问真实外网站点。脚本仅接受 `emulator-5580`，先断言模拟器身份和隔离网络状态。完成后关闭 VPN、移除自己创建的 ADB 映射并停止固定响应服务。

开发测试脚本不是用户安装入口；手机日常安装使用基础包中的 `install.cmd`。
