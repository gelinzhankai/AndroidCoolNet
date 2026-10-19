"""Windows/ADB CMFA provisioner. No root, private app-file writes, or VPN auto-consent."""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import http.server
import json
import os
from pathlib import Path
import re
import secrets
import shlex
import shutil
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

import yaml
from gms_assets import AssetError, ensure_google_assets, LABELS as GOOGLE_LABELS

ROOT = Path(__file__).resolve().parent
PACKAGE = "com.github.metacubex.clash.meta"
ACTIVITY = "com.github.kr328.clash."
VERSION = "2.11.35"
MAX_DOWNLOAD = 16 * 1024 * 1024
APK_HASHES = {
    "arm64-v8a": "af7f05d8801798a8e75de682e5f67070138becb8623b7a341c3e5cd042a3753d",
    "armeabi-v7a": "11c249a17ade5d714d63a8c8c3bb02a0371790467d0b1f5c8747671a36adbb6c",
    "x86": "3bf178e0b92739a4eab167d601e3750e76c1fadaa968c20043a888bff9f7b441",
    "x86_64": "a722aef0988f3ac90ab2b04755bb5a3f69ddd68fc38744c1ab04d2543d45af45",
}
GOOGLE_PACKAGES = ("com.google.android.gsf", "com.google.android.gms", "com.android.vending")


class SetupError(Exception):
    pass


def say(message):
    print(message, flush=True)


def fetch(url, proxy=None, limit=MAX_DOWNLOAD):
    """PC downloads only. Never configure Android/emulator proxy settings."""
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "https" and not (parsed.scheme == "http" and parsed.hostname in ("127.0.0.1", "localhost")):
        raise SetupError("仅支持 HTTPS 订阅地址（本地测试允许 loopback HTTP）。")
    handler = urllib.request.ProxyHandler({"https": proxy, "http": proxy} if proxy else {})
    opener = urllib.request.build_opener(handler)
    req = urllib.request.Request(url, headers={"User-Agent": "clash.meta/AndroidSetup-0.3"})
    try:
        with opener.open(req, timeout=45) as response:
            data = response.read(limit + 1)
        if len(data) > limit:
            raise SetupError("下载内容超过大小限制。")
        return data
    except SetupError:
        raise
    except Exception:
        # URLs, HTTP error bodies and credentials must not enter logs.
        raise SetupError("电脑下载失败；检查网络、订阅有效性，或用 --pc-download-proxy 指定仅用于下载的代理。") from None


def extract_proxies(data):
    try:
        obj = yaml.safe_load(data)
    except Exception:
        raise SetupError("订阅不是有效的 Clash/Mihomo YAML。") from None
    if not isinstance(obj, dict) or not isinstance(obj.get("proxies"), list) or not obj["proxies"]:
        raise SetupError("订阅必须包含非空 proxies 节点列表。仅 proxy-providers、Base64 节点列表和网页暂不支持。")
    proxies = obj["proxies"]
    names = []
    if len(proxies) > 2000:
        raise SetupError("节点数超过 2000。")
    for node in proxies:
        if not isinstance(node, dict) or not isinstance(node.get("name"), str) or not node["name"].strip():
            raise SetupError("订阅节点缺少有效名称。")
        if not isinstance(node.get("type"), str) or not isinstance(node.get("server"), str):
            raise SetupError("订阅节点缺少 type/server。")
        if not isinstance(node.get("port"), int) or isinstance(node["port"], bool) or not 1 <= node["port"] <= 65535:
            raise SetupError("订阅节点端口无效。")
        if node.get("dialer-proxy"):
            raise SetupError("本版本不支持依赖其他代理组的 dialer-proxy 节点。")
        if node["name"] in names or node["name"] in ("PROXY", "DIRECT", "REJECT"):
            raise SetupError("订阅节点名称重复或与保留组名冲突。")
        names.append(node["name"])
    return proxies


def load_subscription(profile_file=None, proxy=None):
    if profile_file:
        try:
            data = profile_file.read_bytes()
        except OSError:
            say("本地订阅文件无法读取，跳过配置导入，继续安装和配置白名单。")
            return None, "skipped_unreadable"
    else:
        try:
            address = input("粘贴 Clash/Mihomo HTTPS 订阅地址（明文显示，留空回车跳过）：").strip()
        except EOFError:
            address = ""
        if not address:
            say("未输入订阅，跳过配置导入，继续安装和配置白名单。")
            return None, "skipped_empty"
        try:
            data = fetch(address, proxy)
        except (SetupError, ValueError):
            say("订阅地址无效或下载失败，跳过配置导入，继续安装和配置白名单。")
            return None, "skipped_download_error"
    try:
        return extract_proxies(data), "parsed"
    except SetupError as exc:
        say(str(exc) + " 已跳过配置导入，继续安装和配置白名单。")
        return None, "skipped_invalid"


def load_profile_settings(path):
    try:
        settings = yaml.safe_load(path.read_text(encoding="utf-8-sig"))
    except (OSError, yaml.YAMLError):
        raise SetupError("无法读取配置模板；请检查 config/profile.yaml 或 --profile-settings 指定的文件。") from None
    if not isinstance(settings, dict):
        raise SetupError("配置模板必须是 YAML 对象。")
    ports = {"port", "socks-port", "redir-port", "tproxy-port", "mixed-port"}
    allowed = ports | {"authentication", "allow-lan", "ipv6", "bind-address", "mode", "log-level", "dns"}
    if set(settings) - allowed:
        raise SetupError("配置模板含不支持的字段；节点/规则由工具管理，External Controller 请在手机覆写页设置。")
    settings = {k: v for k, v in settings.items() if v is not None}
    for key in ports & settings.keys():
        if type(settings[key]) is not int or not 0 <= settings[key] <= 65535:
            raise SetupError("配置模板中的端口必须为 0～65535 的整数。")
    for key in ("allow-lan", "ipv6"):
        if key in settings and type(settings[key]) is not bool:
            raise SetupError("配置模板中的 allow-lan/ipv6 必须为 true 或 false。")
    if "authentication" in settings and (not isinstance(settings["authentication"], list)
            or any(not isinstance(x, str) or ":" not in x for x in settings["authentication"])):
        raise SetupError("authentication 必须是 user:password 字符串列表。")
    if "bind-address" in settings and not isinstance(settings["bind-address"], str):
        raise SetupError("bind-address 必须是字符串。")
    if "mode" in settings and settings["mode"] not in ("rule", "global", "direct"):
        raise SetupError("mode 必须是 rule、global 或 direct。")
    if "log-level" in settings and settings["log-level"] not in ("silent", "error", "warning", "info", "debug"):
        raise SetupError("log-level 无效。")
    if "dns" in settings and not isinstance(settings["dns"], dict):
        raise SetupError("dns 必须是 YAML 对象。")
    return settings


def make_profile(proxies, rules, settings=None):
    if not isinstance(rules, list) or not rules or rules[-1] != "MATCH,PROXY":
        raise SetupError("规则最后一项必须是 MATCH,PROXY。")
    obj = {
        **(load_profile_settings(ROOT / "config" / "profile.yaml") if settings is None else settings),
        "proxies": proxies,
        "proxy-groups": [{"name": "PROXY", "type": "select", "proxies": [p["name"] for p in proxies]}],
        "rules": rules,
    }
    return yaml.safe_dump(obj, allow_unicode=True, sort_keys=False).encode("utf-8")


def choose_whitelist(installed, template):
    # Includes system and ordinary packages; Google is matched in the package name,
    # not the localized display label. Play Store is a special non-google package.
    return sorted(p for p in installed if "google" in p.lower() or p == "com.android.vending" or p in template)


class Adb:
    def __init__(self, executable, serial):
        self.exe, self.serial = str(executable), serial

    def run(self, *args, timeout=45, check=True, include_stderr=False):
        try:
            result = subprocess.run([self.exe, "-s", self.serial, *map(str, args)],
                                    capture_output=True, timeout=timeout, creationflags=0x08000000 if os.name == "nt" else 0)
        except subprocess.TimeoutExpired:
            raise SetupError("ADB 操作超时；请检查手机解锁状态和 USB 连接。") from None
        out = result.stdout.decode("utf-8", "replace").strip()
        if include_stderr:
            out += "\n" + result.stderr.decode("utf-8", "replace").strip()
        if check and result.returncode:
            raise SetupError("ADB 操作失败；检查授权、USB 调试（安全设置）和设备连接。")
        return out

    def shell(self, *args, **kwargs):
        return self.run("shell", shlex.join(map(str, args)), **kwargs)

    def packages(self, *flags):
        return {line[8:] for line in self.shell("pm", "list", "packages", "--user", "0", *flags).splitlines() if line.startswith("package:")}

    def network_candidates(self, desired):
        raw = self.shell("dumpsys", "package", "packages")
        # Ignore factory copies of updated system packages, and never infer that a
        # shared-UID package lacks INTERNET from its package-only permission dump.
        raw = raw.split("Hidden system packages:", 1)[0]
        blocks = {m.group(1): m.group(0) for m in re.finditer(r"^  Package \[([^\]]+)\].*?(?=^  Package \[|\Z)", raw, re.M | re.S)}
        eligible, excluded = [], []
        for p in desired:
            block = blocks.get(p, "")
            uid = re.search(r"\b(?:appId|userId)=(\d+)", block)
            # Matches CMFA's source filter: INTERNET permission OR system UID.
            if not block or not uid or "sharedUser=" in block or "android.permission.INTERNET" in block or int(uid.group(1)) < 10000:
                eligible.append(p)
            else:
                excluded.append(p)
        return eligible, excluded


def find_adb(explicit=None):
    candidates = [explicit, ROOT / "platform-tools" / "adb.exe", shutil.which("adb")]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return Path(candidate)
    raise SetupError("找不到 ADB；请把官方 platform-tools 放入本目录，或用 --adb 指定 adb.exe。")


def select_device(adb_path, serial):
    result = subprocess.run([str(adb_path), "devices"], capture_output=True, text=True, timeout=20)
    devices = [line.split()[:2] for line in result.stdout.splitlines()[1:] if len(line.split()) >= 2]
    if serial:
        if [serial, "device"] not in devices:
            raise SetupError("指定设备未就绪；请解锁手机并允许 USB 调试。")
        return serial
    ready = [d[0] for d in devices if d[1] == "device"]
    if len(ready) != 1 or len(devices) != 1:
        raise SetupError("请只连接一台已授权设备；多设备时必须用 --serial 明确选择。")
    return ready[0]


def inspect_device(adb):
    sdk = int(adb.shell("getprop", "ro.build.version.sdk") or "0")
    if sdk < 24:
        raise SetupError("第一版仅支持 Android 7 / API 24 及以上。")
    if adb.shell("am", "get-current-user") != "0":
        raise SetupError("第一版仅在主用户（user 0）运行；请先切换主用户。")
    installed, known, disabled = adb.packages(), adb.packages("-u"), adb.packages("-d")
    gms = {}
    for p in GOOGLE_PACKAGES:
        gms[p] = "disabled" if p in disabled else "installed" if p in installed else "not_installed_for_user" if p in known else "missing"
    return {"model": adb.shell("getprop", "ro.product.model"), "api": sdk,
            "android": adb.shell("getprop", "ro.build.version.release"),
            "preview_sdk": int(adb.shell("getprop", "ro.build.version.preview_sdk") or "0"),
            "abis": adb.shell("getprop", "ro.product.cpu.abilist").split(","), "gms": gms}, installed


def select_google_apk(entries, package, device):
    """Match only the deliberately bounded catalog, never guess from an APK filename."""
    if device["api"] not in (35, 36, 37) or device.get("preview_sdk", 0):
        raise SetupError("Google 补装仅匹配 Android 15/16/17 正式版（API 35/36/37）；此系统没有匹配包。")
    candidates = [e for e in entries if e["package"] == package
                  and e["supported_api_min"] <= device["api"] <= e["supported_api_max"]
                  and e["min_sdk"] <= device["api"]]
    for abi in device["abis"]:
        for entry in candidates:
            if abi in entry["abis"] or entry["abis"] == ["noarch"]:
                return entry
    raise SetupError(f"{package} 没有匹配此 Android 版本/CPU 架构的已核验安装包。")


def verified_google_apk(entry, root):
    cache = (root / "cache" / "gms").resolve()
    path = (cache / entry["file"]).resolve()
    if path.parent != cache or path.suffix != ".apk":
        raise SetupError("Google 安装包目录配置无效。")
    if not path.is_file():
        raise SetupError(f"缺少已核验安装包 {path.name}；请重试下载或导入 Google 离线组件包。")
    with path.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    if digest != entry["sha256"]:
        raise SetupError(f"Google 安装包 {path.name} 的 SHA-256 校验失败，拒绝安装。")
    return path


def provision_google(adb, device, root=None, proxy=None):
    """Restore installed system code or install a pinned APK with explicit no-replace."""
    root = ROOT if root is None else root
    result = {"components": {}, "complete": False, "login_verified": False}
    actions = []
    for package in GOOGLE_PACKAGES:
        state = device["gms"][package]
        if state in ("installed", "disabled"):
            result["components"][package] = {"status": "skipped_disabled" if state == "disabled" else "already_installed"}
            say(f"Google：{package} 已安装，保留原版本" + ("及禁用状态。" if state == "disabled" else "。"))
        else:
            actions.append((package, state))
    prepared = {}
    if actions:
        say("检测到以下 Google 组件待处理：")
        for package, state in actions:
            say(f"  - {GOOGLE_LABELS.get(package, package)} ({package}): " +
                ("系统已有，恢复当前用户即可，无需下载" if state == "not_installed_for_user" else "缺失，需要补装"))
    # Preflight every fresh APK before making changes. Recovery of existing code
    # requires no external APK, works on other SDK versions, and preserves its version.
    try:
        missing = [p for p, state in actions if state == "missing"]
        if missing:
            entries = json.loads((root / "config" / "gms-packages.json").read_text(encoding="utf-8-sig"))["packages"]
            libraries = adb.shell("pm", "list", "libraries").splitlines()
            available = {x.removeprefix("library:").strip() for x in libraries if x.startswith("library:")}
            selected = []
            for package in missing:
                entry = select_google_apk(entries, package, device)
                absent = set(entry.get("required_libraries", [])) - available
                if absent:
                    raise SetupError(f"{package} 所需系统库缺失：{', '.join(sorted(absent))}；普通 APK 补装不能补齐 ROM 系统库。")
                selected.append(entry)
            ensure_google_assets(selected, root, proxy)
            for entry in selected:
                prepared[entry["package"]] = (entry, verified_google_apk(entry, root))
    except (SetupError, AssetError, OSError, ValueError, KeyError, TypeError) as exc:
        reason = str(exc) if isinstance(exc, (SetupError, AssetError)) else "Google 安装包清单无法读取或格式错误。"
        say("Google 补装预检未通过：" + reason)
        for package, _ in actions:
            result["components"][package] = {"status": "preflight_failed", "reason": reason}
        return result
    for index, (package, _) in enumerate(actions):
        try:
            # Recheck immediately before mutation, including packages uninstalled
            # for user 0 but still present on another user / in the system image.
            installed, known = adb.packages(), adb.packages("-u")
            if package in installed:
                result["components"][package] = {"status": "already_installed"}
                continue
            if package in known:
                say(f"Google：恢复系统已有组件 {package}（不替换 APK）…")
                adb.shell("cmd", "package", "install-existing", "--user", "0", package)
                status = "restored_existing"
                entry = None
            else:
                if package not in prepared:
                    raise SetupError("系统已有组件在检测后消失；为避免选错版本，请重新运行。")
                entry, path = prepared[package]
                # -R explicitly clears INSTALL_REPLACE_EXISTING. Omitting -r alone
                # does not guarantee this on modern Android package managers.
                say(f"Google：补装 {package} / {entry['version_name']} …")
                output = adb.run("install", "--no-streaming", "-R", "--user", "0", str(path),
                                 timeout=300, check=False, include_stderr=True)
                if not re.search(r"^Success\s*$", output, re.M):
                    code = re.search(r"INSTALL_(?:FAILED|PARSE_FAILED)_[A-Z0-9_]+", output)
                    raise SetupError("系统拒绝安装：" + (code.group(0) if code else "请查看手机安装提示或 USB 安装权限"))
                status = "installed"
            if package not in adb.packages():
                raise SetupError("安装后仍未检测到组件；系统可能拒绝了安装或恢复。")
            result["components"][package] = {"status": status}
            if entry:
                result["components"][package].update(version=entry["version_name"], sha256=entry["sha256"])
        except SetupError as exc:
            say(f"Google：{package} 补装未完成：{exc}")
            result["components"][package] = {"status": "failed", "reason": str(exc)}
            for pending, _ in actions[index + 1:]:
                result["components"][pending] = {"status": "blocked_by_previous_failure"}
            break
    installed, disabled = adb.packages(), adb.packages("-d")
    result["complete"] = all(p in installed and p not in disabled for p in GOOGLE_PACKAGES)
    result["after"] = {p: "disabled" if p in disabled else "installed" if p in installed else "missing" for p in GOOGLE_PACKAGES}
    say("Google 组件检测齐全；登录/设备认证尚未验证。" if result["complete"] else "Google 组件仍有缺失或被禁用，详见报告；继续处理 Clash。")
    return result


def save_report(report):
    report_dir = ROOT / "reports"
    report_dir.mkdir(exist_ok=True)
    path = report_dir / (time.strftime("%Y%m%d-%H%M%S") + f"-{time.time_ns() % 1000000:06}.json")
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    say(f"报告：{path}")
    return path


def install_client(adb, device, installed, proxy=None):
    if PACKAGE in installed:
        info = adb.shell("dumpsys", "package", PACKAGE)
        if not re.search(r"versionName=" + re.escape(VERSION + ".Meta") + r"(?:\s|$)", info):
            raise SetupError("已有 Clash Meta 版本与本工具验证版本不符；为保留已有环境，本次不覆盖。")
        say("Clash Meta 已安装，跳过安装。")
        return "already_installed"
    abi = next((x for x in device["abis"] if x in APK_HASHES), None)
    if not abi:
        raise SetupError("未识别到支持的 CPU 架构。")
    filename = f"cmfa-{VERSION}-meta-{abi}-release.apk"
    apk = ROOT / "cache" / filename
    apk.parent.mkdir(exist_ok=True)
    if not apk.exists():
        say(f"下载官方 Clash Meta {VERSION} ({abi}) …")
        data = fetch(f"https://github.com/MetaCubeX/ClashMetaForAndroid/releases/download/v{VERSION}/{filename}", proxy, 160 * 1024 * 1024)
        if hashlib.sha256(data).hexdigest() != APK_HASHES[abi]:
            raise SetupError("APK SHA-256 与官方发布记录不符，已拒绝安装。")
        apk.write_bytes(data)
    if hashlib.sha256(apk.read_bytes()).hexdigest() != APK_HASHES[abi]:
        raise SetupError("缓存 APK 校验失败；请移走该文件后重新运行。")
    if "Success" not in adb.run("install", "--user", "0", str(apk), timeout=180):
        raise SetupError("应用未安装成功；请检查手机上的安装确认。")
    return "installed"


class UI:
    def __init__(self, adb):
        self.adb = adb
        self.root = None

    def dump(self):
        for _ in range(3):
            self.adb.shell("rm", "-f", "/sdcard/android-setup-ui.xml", check=False)
            self.adb.shell("uiautomator", "dump", "/sdcard/android-setup-ui.xml", check=False, timeout=25)
            raw = self.adb.shell("cat", "/sdcard/android-setup-ui.xml", check=False)
            self.adb.shell("rm", "-f", "/sdcard/android-setup-ui.xml", check=False)
            try:
                self.root = ET.fromstring(raw[raw.index("<?xml"):])
                return self.root
            except (ValueError, ET.ParseError):
                time.sleep(1)
        raise SetupError("无法读取手机界面；请解锁屏幕，并允许 USB 调试输入。")

    def nodes(self):
        return list(self.root.iter("node"))

    def find(self, *labels, rid=None, cls=None):
        for n in self.nodes():
            if rid and n.get("resource-id", "").endswith(":" + "id/" + rid):
                return n
            if cls and n.get("class") == cls:
                return n
            if labels and n.get("class") != "android.widget.EditText" and (n.get("text") in labels or n.get("content-desc") in labels):
                return n
        return None

    def tap(self, node):
        if node is None or node.get("enabled") == "false":
            raise SetupError("界面与已验证版本不匹配，已停止自动操作；请勿在自动配置时操作手机。")
        box = re.fullmatch(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", node.get("bounds", ""))
        if not box:
            raise SetupError("无法定位界面控件。")
        x1, y1, x2, y2 = map(int, box.groups())
        self.adb.shell("input", "tap", (x1 + x2) // 2, (y1 + y2) // 2)
        time.sleep(.3)

    def click(self, *labels, rid=None, cls=None):
        self.dump()
        node = self.find(*labels, rid=rid, cls=cls)
        self.tap(node)

    def back(self):
        self.adb.shell("input", "keyevent", "KEYCODE_BACK")

    def home(self):
        self.adb.shell("am", "start", "-n", f"{PACKAGE}/{ACTIVITY}MainActivityAlias")
        self.dump()
        # Only the notification prompt has this allow ID and matching message.
        if any("notifications" in n.get("text", "").lower() or "通知" in n.get("text", "") for n in self.nodes()):
            allow = self.find(rid="permission_allow_button")
            if allow is not None:
                self.tap(allow)
                self.dump()
        if self.find("Stopped", "已停止") is None:
            # Do not silently stop or rewrite a user's running VPN configuration.
            if self.find("Running", "运行中", "已启动") is not None:
                raise SetupError("Clash 正在运行；请先在手机中停止，再执行配置。")

    def configure_whitelist(self, desired, replace=True):
        self.home()
        self.click("Settings", "设置")
        self.click("Network", "网络")
        self.dump()
        vpn = self.find("Route System Traffic", "自动路由系统流量")
        if vpn is None:
            raise SetupError("找不到 VPN 自动路由选项。")
        switch = next((n for n in self.row(vpn).iter("node") if n.get("checkable") == "true"), None)
        if switch is None:
            raise SetupError("无法确认 VPN 自动路由状态。")
        if switch.get("checked") != "true":
            self.tap(vpn)
        # Mode is below the fold on some displays.
        for _ in range(4):
            self.dump()
            if self.find("Access Control Mode", "访问控制模式") is not None:
                break
            scroll = next((n for n in self.nodes() if n.get("scrollable") == "true"), None)
            if scroll is None:
                break
            b = list(map(int, re.findall(r"\d+", scroll.get("bounds"))))
            self.adb.shell("input", "swipe", (b[0]+b[2])//2, b[3]-80, (b[0]+b[2])//2, b[1]+80, 350)
        self.click("Access Control Mode", "访问控制模式")
        self.click("Allow selected apps", "仅允许已选择的应用")
        self.click("Access Control Packages", "访问控制应用包列表")
        self.click("More", "更多", rid="menu_view")
        self.click("Filter", "过滤")
        self.dump()
        system = self.find("System Apps", "系统应用")
        if system is None:
            raise SetupError("找不到系统应用选项。")
        # Popup menu check state lives in the containing row.
        row = self.row(system)
        check = next((n for n in row.iter("node") if n.get("checkable") == "true"), None)
        if check is None:
            raise SetupError("无法确认系统应用显示状态。")
        # Upstream calls this a filter: checked means HIDE system applications.
        if check.get("checked") == "true":
            self.tap(system)
        else:
            self.back()
        # Replace the selected list with the explicit template and discovered Google packages.
        if replace:
            self.click("More", "更多", rid="menu_view")
            self.click("Select none", "Select None", "清除")
        selected = []
        unavailable = []
        for package in desired:
            say("  白名单：" + package)
            self.click("Search", "查找", rid="search_view")
            self.dump()
            field = self.find(rid="keyword_view", cls="android.widget.EditText")
            self.tap(field)
            self.adb.shell("input", "text", package)
            self.dump()
            label = self.find(package)
            if label is None:
                # CMFA excludes packages without INTERNET permission; retain this in report.
                unavailable.append(package)
            else:
                row = self.row(label)
                checkbox = next((n for n in row.iter("node") if n.get("checkable") == "true"), None)
                if checkbox is None:
                    raise SetupError("找不到应用白名单复选框。")
                if checkbox.get("checked") != "true":
                    self.tap(label)
                self.dump()
                label = self.find(package)
                row = self.row(label)
                if not any(n.get("checked") == "true" for n in row.iter("node")):
                    raise SetupError("白名单勾选未生效。")
                selected.append(package)
            self.click("Close", "关闭", rid="close_view")
        self.back()  # AccessControlActivity persists on exit.
        self.dump()
        if self.find("Allow selected apps", "仅允许已选择的应用") is None:
            raise SetupError("白名单模式未保存。")
        self.back()
        self.back()
        return selected, unavailable

    def row(self, node):
        if node is None:
            raise SetupError("界面项目消失。")
        parents = {c: p for p in self.root.iter() for c in p}
        current = node
        while current in parents:
            if current.get("clickable") == "true" and any(n.get("checkable") == "true" for n in current.iter("node")):
                return current
            current = parents[current]
        return current

    def activate_or_import(self, name, url):
        self.home()
        self.click("Profiles", "Profile", "配置")
        existing = self.find_profile(name)
        if existing is not None:
            self.tap(existing)
            self.back()
            self.dump()
            if self.find(name, name + " Activated", name + " 已激活") is None:
                raise SetupError("未确认已有配置已激活。")
            return "reused"
        self.back()
        transfer_name = name + "-transfer-" + secrets.token_hex(3)
        uri = "clashmeta://install-config?" + urllib.parse.urlencode({"url": url, "name": transfer_name, "type": "url"})
        self.adb.shell("am", "start", "-a", "android.intent.action.VIEW", "-d", uri,
                       "-n", f"{PACKAGE}/{ACTIVITY}ExternalControlActivity")
        self.save_profile()
        self.home()
        self.click("Profiles", "Profile", "配置")
        self.profile_menu(transfer_name)
        self.click("Duplicate", "复制")
        self.click("Name", "名称")
        self.replace_text(name)
        self.click("OK", "确定", "确认")
        self.save_profile()
        self.home()
        self.click("Profiles", "Profile", "配置")
        self.profile_menu(transfer_name)
        self.click("Delete", "删除")
        self.dump()
        if self.find("OK", "确定", "确认") is not None:
            self.click("OK", "确定", "确认")
        self.tap(self.find_profile(name))
        self.back()
        self.dump()
        if self.find(name, name + " Activated", name + " 已激活") is None:
            raise SetupError("未确认新配置已激活。")
        return "imported"

    def replace_text(self, text):
        self.dump()
        field = self.find(cls="android.widget.EditText")
        self.tap(field)
        original_length = len(field.get("text", ""))
        self.adb.shell("input", "keycombination", "113", "29", check=False)  # Ctrl+A
        self.adb.shell("input", "keyevent", "KEYCODE_DEL")
        self.dump()
        field = self.find(cls="android.widget.EditText")
        if field is None:
            raise SetupError("文本编辑框消失。")
        # UIAutomator exposes EditText's hint as text when the field is empty.
        empty_texts = ("", "Properties", "参数")
        if field.get("text", "") not in empty_texts:
            # Older Android versions lack keycombination; inject separate events.
            self.adb.shell("input", "keyevent", "KEYCODE_MOVE_END")
            for _ in range(original_length + 5):
                self.adb.shell("input", "keyevent", "KEYCODE_DEL")
            self.dump()
            field = self.find(cls="android.widget.EditText")
            if field is None or field.get("text", "") not in empty_texts:
                raise SetupError("无法清空配置名称。")
        self.adb.shell("input", "text", text)
        self.dump()
        field = self.find(cls="android.widget.EditText")
        if field is None or field.get("text") != text:
            raise SetupError("配置名称输入未生效。")

    def profile_menu(self, name):
        label = self.find_profile(name)
        if label is None:
            raise SetupError("找不到待处理配置。")
        parents = {c: p for p in self.root.iter() for c in p}
        while label in parents:
            menu = next((n for n in label.iter("node") if n.get("resource-id", "").endswith(":id/menu_view")), None)
            if menu is not None:
                self.tap(menu)
                return
            label = parents[label]
        raise SetupError("找不到配置操作菜单。")

    def find_profile(self, name):
        previous = None
        for _ in range(50):
            self.dump()
            found = self.find(name)
            if found is not None:
                return found
            names = tuple(next((c.get("text") for c in n.iter("node") if c.get("text")), "")
                          for n in self.nodes() if n.get("resource-id", "").endswith(":id/root_view"))
            scroll = next((n for n in self.nodes() if n.get("scrollable") == "true"), None)
            if names == previous or scroll is None:
                return None
            previous = names
            b = list(map(int, re.findall(r"\d+", scroll.get("bounds"))))
            self.adb.shell("input", "swipe", (b[0]+b[2])//2, b[3]-80, (b[0]+b[2])//2, b[1]+80, 350)
        raise SetupError("配置列表过长，未能可靠定位；请整理旧配置后重试。")

    def save_profile(self):
        self.click("Save", "保存")
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            self.dump()
            if (self.find("Profiles", "Profile", "配置") is not None
                    and self.find("Save", "保存", "Name", "名称") is None):
                break
            # Do not persist dialogs: they can contain subscription node credentials.
            if self.find("Error", "错误", "DETAIL", "详情") is not None:
                raise SetupError("Clash 拒绝该配置；请在手机查看错误内容。")
            time.sleep(1)
        else:
            raise SetupError("配置导入未完成；请查看手机上的错误提示。")


@contextlib.contextmanager
def serve_profile(adb, content):
    token = secrets.token_urlsafe(24)
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path != "/" + token + ".yaml":
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/yaml")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        def log_message(self, *args):
            pass
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    # Only a temporary configuration file server, never an Internet proxy.
    remote_port = None
    try:
        existing = adb.run("reverse", "--list")
        for candidate in range(18765, 18865):
            if f"tcp:{candidate} " not in existing:
                adb.run("reverse", "--no-rebind", f"tcp:{candidate}", f"tcp:{port}")
                remote_port = candidate
                break
        if remote_port is None:
            raise SetupError("无法分配临时配置传输端口。")
        yield f"http://127.0.0.1:{remote_port}/{token}.yaml"
    finally:
        if remote_port:
            adb.run("reverse", "--remove", f"tcp:{remote_port}", check=False)
        server.shutdown()
        server.server_close()


def main(argv=None):
    parser = argparse.ArgumentParser(description="AndroidCoolNet: Google 缺失组件补装 + Clash Meta + 应用白名单")
    parser.add_argument("--serial")
    parser.add_argument("--adb")
    parser.add_argument("--detect-only", action="store_true")
    gms_options = parser.add_mutually_exclusive_group()
    gms_options.add_argument("--gms-only", action="store_true", help="仅检测及补装 Google 组件，不处理 Clash/订阅")
    gms_options.add_argument("--skip-gms", action="store_true", help="跳过 Google 补装，仍检测组件状态")
    parser.add_argument("--profile-file", type=Path, help="本地 Clash YAML，主要用于离线测试")
    parser.add_argument("--pc-download-proxy", help="仅用于电脑下载，不配置手机或模拟器代理")
    parser.add_argument("--allowlist", type=Path, default=ROOT / "config" / "apps.json")
    parser.add_argument("--rules", type=Path, default=ROOT / "config" / "rules.json")
    parser.add_argument("--profile-settings", type=Path, default=ROOT / "config" / "profile.yaml")
    args = parser.parse_args(argv)
    adb_path = find_adb(args.adb)
    serial = select_device(adb_path, args.serial)
    adb = Adb(adb_path, serial)
    device, installed = inspect_device(adb)
    say(f"设备：{device['model']} / Android {device['android']}（API {device['api']}）/ {serial}")
    say("CPU 架构：" + ", ".join(device['abis']))
    states = {"installed": "已安装（保留）", "disabled": "已安装但禁用（保留）",
              "not_installed_for_user": "系统已有，当前用户未安装", "missing": "缺失"}
    for p, state in device["gms"].items():
        say(f"  {GOOGLE_LABELS.get(p, p)} ({p}): {states.get(state, state)}")
    say("组件存在不等于 GMS 已可用；不会覆盖/启用 Google 组件。")
    if args.detect_only:
        return 0
    google_result = {"skipped": True, "complete": False} if args.skip_gms else provision_google(adb, device, proxy=args.pc_download_proxy)
    if not args.skip_gms:
        # Persist even if a later subscription / UI step is cancelled or fails.
        save_report({"phase": "google", "serial": serial, "device": device, "google_install": google_result})
        device, installed = inspect_device(adb)
    google_exit = 0 if args.skip_gms or google_result["complete"] else 2
    if args.gms_only:
        return google_exit
    catalog = json.loads(args.allowlist.read_text(encoding="utf-8-sig"))
    desired = choose_whitelist(installed, {a["package"] for a in catalog["apps"]})
    if not desired:
        raise SetupError("未找到白名单应用。")
    proxies, subscription_status = load_subscription(args.profile_file, args.pc_download_proxy)
    content, name, profile_status = None, None, "skipped"
    if proxies is not None:
        rules = json.loads(args.rules.read_text(encoding="utf-8-sig"))["rules"]
        content = make_profile(proxies, rules, load_profile_settings(args.profile_settings))
        name = "AndroidSetup-" + hashlib.sha256(content).hexdigest()[:10]
    install_status = install_client(adb, device, installed, args.pc_download_proxy)
    ui = UI(adb)
    say(f"准备配置 {len(desired)} 个白名单包；手机请保持解锁，不要手动操作界面。")
    eligible, no_network_permission = adb.network_candidates(desired)
    say(f"其中 {len(eligible)} 个需在客户端确认（含共享 UID）；其余无网络权限包由客户端过滤。")
    selected, unavailable = ui.configure_whitelist(eligible)
    if content is not None:
        with serve_profile(adb, content) as url:
            profile_status = ui.activate_or_import(name, url)
    report = {"device": device, "serial": serial, "client_version": VERSION,
              "google_install": google_result,
              "install": install_status, "profile": name, "profile_status": profile_status,
              "subscription_status": subscription_status,
              "whitelist_selected": selected, "not_selectable_in_cmfa": unavailable,
              "google_and_template_candidates": desired, "no_network_permission": no_network_permission,
              "vpn": "manual_authorization_and_start_required" if content is not None else "existing_profile_unchanged_or_import_required",
              "google_login": "not_tested",
              "subscription_saved_on_pc": False, "emulator_proxy_configured": False}
    save_report(report)
    if content is not None:
        say(f"完成：配置已导入并激活，已选 {len(selected)} 个应用。")
    else:
        say(f"完成：安装及白名单配置完成，已选 {len(selected)} 个应用；订阅导入已跳过。")
    if unavailable:
        say("以下包无网络权限或未在 Clash 应用列表中显示，未勾选：" + ", ".join(unavailable))
    if content is not None:
        say("请在手机 Clash 首页点击启动，首次 VPN 授权由你确认。未验证真实节点联网。")
        say("订阅按本次内容生成本地配置；节点更新后请重新运行本工具。")
    else:
        say("未导入或切换节点配置。已有配置继续保留；如无可用配置，请在手机手动导入或重新运行工具。")
        reasons = {
            "skipped_empty": "未输入订阅地址，已跳过订阅导入",
            "skipped_download_error": "订阅地址无效或下载失败，已跳过订阅导入",
            "skipped_invalid": "订阅解析失败，已跳过订阅导入",
            "skipped_unreadable": "本地订阅文件无法读取，已跳过订阅导入",
        }
        say("需要手动处理：" + reasons.get(subscription_status, "订阅导入已跳过") + "。")
        say("若已有可用节点配置可继续使用；若没有，请先在 Clash 中手动导入有效订阅/节点。")
        say("本次没有应用规则模式和 DNS 模板，也没有修改手机覆写设置。请自行在 Clash 设置 > 覆写中核对：")
        say("  模式：规则（Rule）；IPv6：禁用。")
        say("  DNS > 策略：强制启用；DNS > IPv6：禁用；增强模式：Fake-IP。")
        say("  DNS > Name Server（名称服务器）：列表设置为 8.8.8.8。")
        say("仅设置 DNS/规则模式不能代替代理节点；有可用配置后再启动 Clash，并确认首次 VPN 授权。")
    say("以后新安装的应用不会自动加入此次白名单：请到 Clash 设置 > 网络 > 允许访问列表，勾选需要代理的应用（必要时显示系统应用）。")
    say("修改允许访问列表后，若运行中的 VPN 未生效，请停止并重新启动 Clash。")
    if google_exit:
        say("Clash 流程已完成，但 Google 补装未完全完成（退出码 2），请查看 Google 阶段报告。")
    return google_exit


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (SetupError, OSError) as exc:
        # Do not emit arbitrary exception representations with subscription bodies.
        say("停止：" + (str(exc) if isinstance(exc, SetupError) else "本地文件或进程操作失败。"))
        raise SystemExit(1)
    except KeyboardInterrupt:
        say("已取消。")
        raise SystemExit(130)
