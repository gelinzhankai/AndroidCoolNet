# AndroidCoolNet（安酷奈）

一种优雅便携的Android设备科学上网基础设施自动化工具

## 使用方法

1. 前往 [下载页面](https://github.com/gelinzhankai/AndroidCoolNet/releases/latest)，下载 **`AndroidCoolNet-Windows-v0.4.0.zip`（约 63 MiB）** 并解压。电脑需为 Windows 10/11 x64。
2. 手机开启 **USB 调试**，用数据线连接电脑并允许调试授权。只连接一台手机，保持屏幕解锁；已有 Clash 请先停止运行。
3. 双击 **`install.cmd`**。工具会检测并列出 Google 组件缺失项，自动匹配 Android 15/16/17 正式版与 ARM 架构，已有组件不覆盖。
4. 缺少安装包时，输入 **`1` 自动下载 **，或 **`2` 手动下载**。手动下载或自动下载失败时，按回车打开下载页面，下载 **`AndroidCoolNet-Google-Offline-v0.4.0.zip`（约 181 MiB）**，回到命令行粘贴 ZIP 路径即可，**无需解压**。也支持文件夹，或多个 APK/ZIP 路径用分号隔开，不要求顺序；留空可跳过补装。
5. 按提示粘贴 **Clash/Mihomo HTTPS 机场订阅链接**。需为包含节点列表的 Clash YAML；留空、下载或解析失败会跳过导入，可稍后在手机手动配置。自动配置期间不要操作手机界面。
6. 完成后在 Clash 首页启动连接，并确认首次 VPN 授权。**以后新安装的应用，需要到「Clash 设置 > 网络 > 允许访问列表」自行勾选。**

手动导入路径示例：

```text
D:\Downloads\AndroidCoolNet-Google-Offline-v0.4.0.zip
"D:\Downloads\gsf-35.apk.zip";"D:\Downloads\gms-arm64.apk.zip";"D:\Downloads\play-store.apk.zip"
```

仅检查、不安装：运行 `install.cmd --detect-only`。Google 组件装齐不等于所有厂商 ROM 都能正常登录，具体兼容性取决于手机系统。
