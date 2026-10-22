"""Optional original app bundles: reviewed SHA-256 pins, no store installer or APK replacement."""
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import shutil
import tempfile
import time
import urllib.parse
import urllib.request
import webbrowser
import zipfile

PACKAGES = {"chatgpt": "com.openai.chatgpt", "claude": "com.anthropic.claude"}
MAX_BUNDLE = 256 * 1024 * 1024


class AppError(Exception):
    pass


def say(message):
    print(message, flush=True)


def ask(message):
    try:
        return input(message).strip()
    except EOFError:
        return ""


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def validate_url(url):
    parsed = urllib.parse.urlsplit(url)
    host = parsed.hostname or ""
    allowed = host in {"www.apkmirror.com", "claude.en.uptodown.com", "dw.uptodown.com"}
    allowed |= host.endswith(".r2.cloudflarestorage.com") or host.endswith(".utdstc.com")
    if parsed.scheme != "https" or parsed.username or parsed.password or parsed.port not in (None, 443) or not allowed:
        raise AppError("下载跳转不属于已支持的 HTTPS 来源。")
    return url


class CheckedRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        validate_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self.links.append(dict(attrs))


def resolve_download(entry, opener):
    """Use normal public download steps; challenge responses fall back to the user's browser."""
    source = validate_url(entry["source"])

    def read(url, data=None):
        req = urllib.request.Request(validate_url(url), data=data, headers={
            "User-Agent": "AndroidCoolNet/0.6.0", "Content-Type": "application/json", "Referer": source})
        with opener.open(req, timeout=25) as response:
            validate_url(response.geturl())
            raw = response.read(2 * 1024 * 1024 + 1)
        if len(raw) > 2 * 1024 * 1024:
            raise AppError("下载页面过大。")
        return raw.decode("utf-8")

    if entry["provider"] == "apkmirror":
        parser = Links()
        parser.feed(read(source))
        links = [a["href"] for a in parser.links if "/download/?key=" in a.get("href", "")]
        if len(set(links)) != 1:
            raise AppError("下载入口需要浏览器验证或页面已变化。")
        page = urllib.parse.urljoin(source, links[0])
        parser = Links()
        parser.feed(read(page))
        links = [a["href"] for a in parser.links if a.get("id") == "download-link" and a.get("href")]
        if len(links) != 1:
            raise AppError("未取得原始分包下载入口。")
        return validate_url(urllib.parse.urljoin(page, links[0]))
    if entry["provider"] == "uptodown":
        endpoint = f"https://claude.en.uptodown.com/ajax/app/{entry['app_id']}/file/{entry['file_id']}/download-url"
        # Never collect browser cookies or solve a challenge. The server may require
        # interactive verification, in which case this request is allowed to fail.
        result = json.loads(read(endpoint, b'{"onlyXapk":true}'))
        if result.get("success") != 1:
            raise AppError("网站要求浏览器验证，请手动下载原始 XAPK。")
        return validate_url(result["data"]["downloadURL"])
    raise AppError("不支持此下载来源。")


def download_bundle(entry, destination, proxy=None):
    opener = urllib.request.build_opener(CheckedRedirect(), urllib.request.ProxyHandler(
        {"https": proxy, "http": proxy} if proxy else {}))
    url = resolve_download(entry, opener)
    request = urllib.request.Request(url, headers={"User-Agent": "AndroidCoolNet/0.6.0", "Referer": entry["source"]})
    count, digest, last = 0, hashlib.sha256(), 0
    with opener.open(request, timeout=40) as response, destination.open("wb") as stream:
        validate_url(response.geturl())
        length = response.headers.get("Content-Length")
        if length and int(length) != entry["bytes"]:
            raise AppError("返回文件大小不符，可能是网页或商店安装器。")
        while chunk := response.read(1024 * 1024):
            count += len(chunk)
            if count > entry["bytes"]:
                raise AppError("文件大小超出已核验版本。")
            stream.write(chunk)
            digest.update(chunk)
            now = time.monotonic()
            if now - last >= .25 or count == entry["bytes"]:
                print(f"\r  {count / entry['bytes']:6.1%}  {count / 1024**2:.1f}/{entry['bytes'] / 1024**2:.1f} MiB", end="", flush=True)
                last = now
    print(flush=True)
    if count != entry["bytes"] or digest.hexdigest() != entry["archive_sha256"]:
        raise AppError("文件与已核验原始分包不符，拒绝安装。")


def cached(path, entry):
    return path.is_file() and path.stat().st_size == entry["bytes"] and sha(path) == entry["archive_sha256"]


def acquire(entry, root, supplied=(), proxy=None):
    cache = root / "cache/ai"
    cache.mkdir(parents=True, exist_ok=True)
    destination = cache / entry["file"]
    if cached(destination, entry):
        say(f"{entry['name']}：使用已校验缓存。")
        return destination
    for value in supplied:
        candidate = Path(value.strip().strip('"'))
        if cached(candidate, entry):
            shutil.copyfile(candidate, destination)
            return destination
    if supplied:
        raise AppError("提供的文件未匹配此版本；请使用工具列出的原始 APKM/XAPK，不能使用商店安装器或其他版本。")
    say(f"{entry['name']} / {entry['version_name']}，约 {entry['bytes'] / 1024**2:.1f} MiB。")
    choice = ask("1 自动下载，2 手动下载；留空跳过此应用：")
    if choice not in {"1", "2"}:
        return None
    if choice == "1":
        try:
            with tempfile.TemporaryDirectory(dir=cache) as folder:
                temporary = Path(folder) / "download.part"
                download_bundle(entry, temporary, proxy)
                temporary.replace(destination)
            return destination
        except (AppError, OSError, ValueError, KeyError, TypeError):
            say("自动下载未完成（网站验证、网络或文件不匹配）；改为浏览器下载原始文件，不影响后续流程。")
    say("原始文件页面：" + entry["source"])
    if entry["provider"] == "uptodown":
        say("选择显示文件大小的原始 XAPK 下载；不要选择 WITH UPTODOWN APP STORE。")
    if ask("按回车打开下载页面；输入 0 跳过此应用：") == "0":
        return None
    try:
        webbrowser.open(entry["source"])
    except webbrowser.Error:
        say("浏览器未打开，请自行访问上面的地址。")
    for _ in range(3):
        value = ask(f"粘贴 {entry['name']} 下载文件的完整路径（可带引号）；留空跳过：")
        if not value:
            return None
        candidate = Path(value.strip('"'))
        if cached(candidate, entry):
            shutil.copyfile(candidate, destination)
            return destination
        say("文件不匹配；仅接受上述固定版本的完整原始分包，不接受安装器、改包或缺少分包的 APK。")
    return None


def select_parts(entry, device, density):
    if not entry["supported_api_min"] <= device["api"] <= entry["supported_api_max"] or device.get("preview_sdk", 0):
        raise AppError("此应用包仅核验了 Android 15/16/17 正式版的版本要求。")
    if device["api"] < entry["min_sdk"]:
        raise AppError("Android 版本低于应用最低要求。")
    parts = entry["parts"]
    bases = [p for p in parts if p["kind"] == "base"]
    if len(bases) != 1:
        raise AppError("安装清单缺少唯一主 APK。")
    chosen = bases + [p for p in parts if p["kind"] == "language"]
    arches = [p for p in parts if p["kind"] == "abi"]
    match = next((p for abi in device["abis"] for p in arches if p["abi"] == abi), None)
    if arches and not match:
        raise AppError("没有适合此设备 CPU 架构的分包。")
    if match:
        chosen.append(match)
    densities = [p for p in parts if p["kind"] == "dpi"]
    if densities:
        chosen.append(min(densities, key=lambda p: (abs(p["dpi"] - density), -p["dpi"])))
    if any(p["kind"] not in {"base", "abi", "language", "dpi"} for p in parts):
        raise AppError("遇到未经核验的功能分包。")
    return chosen


def extract_verified(path, entry, selected, folder):
    # Full archive pin protects metadata/signers too; only reviewed APK entries are extracted.
    if not cached(path, entry):
        raise AppError("安装前文件 SHA-256 复核失败。")
    expected = {p["file"]: p for p in entry["parts"]}
    output = []
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)) or {n for n in names if n.endswith(".apk")} != set(expected):
            raise AppError("分包清单不一致。")
        for part in selected:
            name = part["file"]
            if Path(name).name != name or any(c in name for c in '/\\:'):
                raise AppError("分包文件名无效。")
            info = archive.getinfo(name)
            if info.file_size != part["bytes"] or info.file_size > MAX_BUNDLE:
                raise AppError("分包大小不符。")
            target = folder / name
            with archive.open(info) as source, target.open("wb") as stream:
                shutil.copyfileobj(source, stream)
            if sha(target) != part["sha256"]:
                raise AppError("分包 SHA-256 复核失败。")
            output.append(target)
    return output


def provision_ai_apps(adb, device, root, selection=None, files=(), proxy=None):
    catalog = json.loads((root / "config/ai-apps.json").read_text(encoding="utf-8"))["apps"]
    for entry in catalog:
        if entry["package"] != PACKAGES.get(entry["id"]) or not 0 < entry["bytes"] <= MAX_BUNDLE:
            raise AppError("AI 应用清单无效。")
        if Path(entry["file"]).name != entry["file"] or any(c in entry["file"] for c in '/\\:'):
            raise AppError("AI 应用缓存文件名无效。")
    if selection is None:
        say("可选安装原版 AI 应用：1 ChatGPT，2 Claude，3 两者；已有应用保留。")
        selection = {"1": "chatgpt", "2": "claude", "3": "both"}.get(ask("选择应用；留空或 0 跳过："), "none")
    wanted = list(PACKAGES) if selection == "both" else [selection] if selection in PACKAGES else []
    report = {"selected": wanted, "apps": {}, "complete": True, "login_verified": False}
    for app_id in wanted:
        entry = next(e for e in catalog if e["id"] == app_id)
        package = entry["package"]
        try:
            if package in adb.packages():
                say(f"{entry['name']} 已安装，保留原版本及启用状态。")
                report["apps"][app_id] = {"status": "already_installed"}
                continue
            if package in adb.packages("-u"):
                say(f"{entry['name']} 设备已有此包但主用户未安装；保留已有版本，请在手机管理用户/应用状态。")
                report["apps"][app_id] = {"status": "not_installed_for_user"}
                report["complete"] = False
                continue
            raw = adb.shell("wm", "density")
            density = re.findall(r"(?:Physical|Override) density:\s*(\d+)", raw)
            if not density:
                raise AppError("未能读取屏幕密度，无法匹配分包。")
            selected = select_parts(entry, device, int(density[-1]))
            path = acquire(entry, root, files, proxy)
            if path is None:
                report["apps"][app_id] = {"status": "skipped"}
                continue
            with tempfile.TemporaryDirectory(prefix="acn-ai-") as folder:
                apks = extract_verified(path, entry, selected, Path(folder))
                # Recheck races immediately before mutation; -R makes the system reject replacements.
                if package in adb.packages("-u"):
                    raise AppError("检测后应用状态发生变化，已跳过，避免覆盖已有应用。")
                say(f"安装 {entry['name']} / {entry['version_name']}（{len(apks)} 个原始分包）…")
                result = adb.run("install-multiple", "--no-streaming", "-R", "--user", "0",
                                 *apks, timeout=300, check=False, include_stderr=True)
            if not re.search(r"^Success\s*$", result, re.M) or package not in adb.packages():
                code = re.search(r"INSTALL_(?:FAILED|PARSE_FAILED)_[A-Z0-9_]+", result)
                raise AppError("系统未完成安装：" + (code[0] if code else "请查看手机 USB 安装确认或系统提示"))
            report["apps"][app_id] = {"status": "installed", "version": entry["version_name"],
                                      "sha256": entry["archive_sha256"], "splits": len(apks)}
            say(f"{entry['name']} 安装完成；稍后重新检测应用并配置 Clash 白名单。未验证登录或联网。")
        except Exception as exc:
            # This optional stage must not prevent Google/Clash setup; don't echo raw URLs/tokens.
            reason = str(exc) if isinstance(exc, AppError) else "下载、文件读取或 ADB 操作未完成。"
            report["apps"][app_id] = {"status": "failed", "reason": reason}
            report["complete"] = False
            say(f"{entry['name']}：{reason} 继续后续流程。")
    return report
