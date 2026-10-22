# AndroidCoolNet（安酷奈）

一种优雅便携的Android设备科学上网基础设施自动化工具

## 使用方法

1. 前往 [下载页面](https://github.com/gelinzhankai/AndroidCoolNet/releases/latest)，下载 **`AndroidCoolNet-Windows-v0.6.0.zip`（约 63 MiB）** 并解压。电脑需为 Windows 10/11 x64，无需另装 Python。
2. 手机开启 **USB 调试**，并在手机设置中搜索、开启 **Google 基础服务**（如系统提供此开关）。用数据线连接电脑并允许调试授权。只连接一台手机，保持屏幕解锁；已有 Clash 请先停止运行。
3. 双击 **`install.cmd`**。程序会先检测国家反诈中心APP；如已安装，显示红色隐私风险提醒，输入 **`1` 或直接回车卸载后继续**，输入 **`2` 保留并继续**。卸载会删除当前用户下的应用和本地数据，失败也会继续。之后检测 Google 组件缺失项，自动匹配 Android 15/16/17 正式版与 ARM 架构，已有组件不覆盖。
4. 缺少安装包时，输入 **`1` 自动下载**，或 **`2` 手动下载**。手动下载或自动下载失败时，按回车打开下载页面，下载 [**`AndroidCoolNet-Google-Offline-v0.5.0.zip`（约 181 MiB，旧版离线包也可复用）**](https://github.com/gelinzhankai/AndroidCoolNet/releases/tag/v0.5.0)，回到命令行粘贴 ZIP 路径即可，**无需解压**。也支持文件夹，或多个 APK/ZIP 路径用分号隔开，不要求顺序；留空可跳过补装。
5. **可选安装 ChatGPT / Claude**：输入 `1` ChatGPT、`2` Claude、`3` 两者，留空跳过；已有应用不覆盖。按提示自动下载或手动下载，遇网站验证会转为手动：**逐个应用粘贴文件路径，无需解压**。仅接受工具所列固定版本的原始 APKM/XAPK，校验后直接通过 ADB 安装，**不安装镜像站商店客户端**；失败可继续。ChatGPT 来自 APKMirror，Claude 来自 Uptodown（选择原始 XAPK，勿选 `WITH UPTODOWN APP STORE`）。本轮装好的应用会加入后续白名单。
6. 按提示粘贴 **Clash/Mihomo HTTPS 机场订阅链接**。需为包含节点列表的 Clash YAML；留空、下载或解析失败会跳过导入，可稍后在手机手动配置。自动配置期间不要操作手机界面。
7. **自动配置白名单和覆写**：程序临时安装约 13 KB 的剪贴板助手，批量导入白名单，并设置、核对覆写，完成后卸载助手；手机弹出 USB 安装确认时请允许。**即使跳过订阅，这两项仍会配置**；没有可用节点时仍需自行导入订阅。覆写 DNS 地址可提前修改 `config/override.yaml`。若自动化失败，可将 `reports/whitelist.txt` 的内容复制到**手机剪贴板**，在访问控制应用包列表中显示系统应用，再点 **更多 > 外部 > 从剪切板导入**（替换原有勾选）。随后进入 **「Clash 设置 > 覆写（Override）」**，手动核对以下项目：

   - **模式（Mode）**：规则（Rule）。
   - **IPv6**：禁用（Disabled）。
   - **DNS > 策略（Strategy）**：强制启用（Force Enable）；**DNS > IPv6**：禁用（Disabled）；**DNS > 增强模式（Enhanced Mode）**：Fake-IP。
   - **DNS > 名称服务器（Name Server）**：可选择一个或多个当前网络可用的地址，点击 `+` 逐个添加，（通常单个8.8.8.8即可）：[8.8.8.8](https://developers.google.com/speed/public-dns/docs/using)、[1.1.1.1](https://developers.cloudflare.com/1.1.1.1/ip-addresses/)、[185.222.222.222](https://dns.sb/)、[208.67.222.222](https://www.opendns.com/setupguide/)、[77.88.8.8](https://dns.yandex.com/)。确认保存。

8. 完成后在 Clash 首页启动连接，并确认首次 VPN 授权。**以后新安装的应用，需要到「Clash 设置 > 网络 > 允许访问列表」自行勾选。**

手动导入路径示例：

```text
D:\Downloads\AndroidCoolNet-Google-Offline-v0.5.0.zip
"D:\Downloads\gsf-35.apk.zip";"D:\Downloads\gms-arm64.apk.zip";"D:\Downloads\play-store.apk.zip"
```

仅检查、不安装：运行 `install.cmd --detect-only`。Google 组件装齐不等于所有厂商 ROM 都能正常登录，具体兼容性取决于手机系统。

仅安装 AI 应用：`install.cmd --apps-only`（完成后需手动加入 Clash 白名单）。正常流程中跳过 AI 应用：`install.cmd --ai-apps none`。应用包按需下载，不占基础包体积；安装成功不保证登录、地区或设备认证可用。

Play 商店没有桌面图标时，工具会检测安装状态和启动入口；被停用时提示手动启用，缺失时才补装，已有版本不覆盖。可运行 `install.cmd --open-play-store` 单独检查并尝试打开已有商店（不执行安装流程）。Clash 白名单中的系统应用筛选与桌面图标无关。
