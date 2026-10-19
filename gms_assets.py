"""Acquire pinned Google APKs without touching Android or trusting archive paths."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import tempfile
import time
import urllib.parse
import urllib.request
import webbrowser
import zipfile
import zlib

RELEASE_PAGE = "https://github.com/gelinzhankai/AndroidCoolNet/releases/tag/v0.4.0"
ASSET_BASE = "https://github.com/gelinzhankai/AndroidCoolNet/releases/download/v0.4.0/"
LABELS = {"com.google.android.gsf": "Google 服务框架", "com.google.android.gms": "Google Play 服务",
          "com.android.vending": "Google Play 商店"}
MAX_ARCHIVE = 512 * 1024 * 1024


class AssetError(Exception):
    pass


def say(message):
    print(message, flush=True)


def ask(message):
    try:
        return input(message).strip()
    except EOFError:
        return ""


def apk_path(root, entry):
    cache = (Path(root) / "cache/gms").resolve()
    path = (cache / entry["file"]).resolve()
    if path.parent != cache or path.suffix.lower() != ".apk":
        raise AssetError("组件文件名无效。")
    return path


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def cached(root, entry):
    path = apk_path(root, entry)
    try:
        return path.is_file() and digest(path) == entry["sha256"]
    except OSError:
        return False


def split_paths(value):
    """Semicolons outside quotes separate paths; spaces and Windows backslashes are literal."""
    paths, buf, quote = [], [], None
    for char in value:
        if quote:
            if char == quote:
                quote = None
            else:
                buf.append(char)
        elif char in ('"', "'") and not ''.join(buf).strip():
            quote = char
        elif char in (';', '；'):
            if ''.join(buf).strip():
                paths.append(''.join(buf).strip())
            buf = []
        else:
            buf.append(char)
    if quote:
        raise AssetError("路径引号未闭合，请重新输入。")
    if ''.join(buf).strip():
        paths.append(''.join(buf).strip())
    return [Path(os.path.expandvars(p)).expanduser() for p in paths]


def copy_verified(stream, size, entries, root):
    """Never execute or extract a supplied filename; copy only hash-matching bytes."""
    candidates = [e for e in entries if e["bytes"] == size]
    if not candidates or size > MAX_ARCHIVE:
        return None
    cache = Path(root) / "cache/gms"
    cache.mkdir(parents=True, exist_ok=True)
    temp = None
    try:
        with tempfile.NamedTemporaryFile(dir=cache, prefix="import-", suffix=".part", delete=False) as out:
            temp = Path(out.name)
            sha, count = hashlib.sha256(), 0
            while data := stream.read(1024 * 1024):
                count += len(data)
                if count > size:
                    raise AssetError("安装包大小超出清单限制。")
                sha.update(data)
                out.write(data)
        entry = next((e for e in candidates if e["sha256"] == sha.hexdigest()), None)
        if count != size or entry is None:
            return None
        temp.replace(apk_path(root, entry))
        return entry["file"]
    finally:
        if temp is not None:
            temp.unlink(missing_ok=True)


def import_file(path, entries, root):
    imported = set()
    try:
        if path.suffix.lower() == ".apk":
            with path.open("rb") as stream:
                name = copy_verified(stream, path.stat().st_size, entries, root)
            if name:
                imported.add(name)
        elif path.suffix.lower() == ".zip":
            with zipfile.ZipFile(path) as archive:
                members = [i for i in archive.infolist() if not i.is_dir() and i.filename.lower().endswith(".apk")]
                if len(members) > 256:
                    raise AssetError("ZIP 内 APK 数量过多，请使用发布页的组件包。")
                for member in members:
                    needed = [e for e in entries if e["file"] not in imported]
                    if not needed:
                        break
                    if not any(e["bytes"] == member.file_size for e in needed):
                        continue
                    with archive.open(member) as stream:
                        name = copy_verified(stream, member.file_size, needed, root)
                    if name:
                        imported.add(name)
        else:
            raise AssetError("请选择 APK、ZIP 或包含它们的文件夹。")
    except (OSError, zipfile.BadZipFile, RuntimeError, EOFError, NotImplementedError, zlib.error):
        raise AssetError("文件无法读取，或 ZIP 损坏、加密、压缩格式不支持。请重新下载发布页的完整文件。") from None
    return imported


def import_paths(value, entries, root):
    files = []
    for path in split_paths(value):
        if path.is_dir():
            base = path.resolve()
            for folder, dirs, names in os.walk(path, followlinks=False):
                here = Path(folder)
                if not here.resolve().is_relative_to(base):
                    dirs[:] = []
                    continue
                if len(here.relative_to(path).parts) >= 4:
                    dirs[:] = []
                for name in names:
                    candidate = here / name
                    if candidate.suffix.lower() in (".apk", ".zip") and not candidate.is_symlink():
                        files.append(candidate)
                if len(files) > 256:
                    raise AssetError("文件夹内候选文件过多，请输入更具体的文件夹或 ZIP 路径。")
        elif path.is_file():
            files.append(path)
        else:
            say(f"路径不存在：{path}")
    imported = set()
    for path in dict.fromkeys(files):
        remaining = [e for e in entries if e["file"] not in imported]
        if not remaining:
            break
        try:
            imported.update(import_file(path, remaining, root))
        except AssetError as exc:
            say(f"未导入 {path.name}：{exc}")
    return imported


def download_archive(entry, destination, proxy=None):
    asset = entry["download_asset"]
    if Path(asset).name != asset or not asset.endswith(".zip") or any(c in asset for c in '/\\'):
        raise AssetError("下载清单的附件名称无效。")
    url = ASSET_BASE + urllib.parse.quote(asset)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({"https": proxy, "http": proxy} if proxy else {}))
    request = urllib.request.Request(url, headers={"User-Agent": "AndroidCoolNet/0.4.0"})
    expected = entry["download_bytes"]
    if not 0 < expected <= MAX_ARCHIVE:
        raise AssetError("下载清单的文件大小无效。")
    try:
        with opener.open(request, timeout=45) as response, destination.open("wb") as out:
            if urllib.parse.urlsplit(response.geturl()).scheme != "https":
                raise AssetError("下载跳转不是 HTTPS，已停止。")
            declared = response.headers.get("Content-Length")
            if declared and int(declared) != expected:
                raise AssetError("服务器返回的文件大小与固定版本不符。")
            count, start, last, sha = 0, time.monotonic(), 0, hashlib.sha256()
            say(f"下载 {LABELS.get(entry['package'], entry['package'])} / {entry['version_name']}")
            while data := response.read(1024 * 1024):
                count += len(data)
                if count > expected:
                    raise AssetError("下载大小超出清单限制。")
                out.write(data)
                sha.update(data)
                now = time.monotonic()
                if now - last >= .25 or count == expected:
                    speed = count / max(now - start, .001) / 1024**2
                    print(f"\r  {count / expected:6.1%}  {count / 1024**2:.1f}/{expected / 1024**2:.1f} MiB  {speed:.1f} MiB/s", end="", flush=True)
                    last = now
            print(flush=True)
        if count != expected or sha.hexdigest() != entry["download_sha256"]:
            raise AssetError("下载不完整或 SHA-256 校验失败。")
    except AssetError:
        raise
    except Exception:
        raise AssetError("下载失败；请检查电脑网络，或用 --pc-download-proxy 指定电脑下载代理。") from None


def ensure_google_assets(entries, root, proxy=None):
    needed = [e for e in entries if not cached(root, e)]
    if not needed:
        say("所需 Google 安装包已在本地且校验通过，无需下载。")
        return
    say("本地还缺少以下已核验安装包：")
    for entry in needed:
        say(f"  - {LABELS.get(entry['package'], entry['package'])}: {entry['file']} / {entry['version_name']}")
    while True:
        choice = ask("选择获取方式：1 自动下载（显示进度） / 2 手动下载；留空跳过本次 Google 补装：")
        if choice in ("1", "2", ""):
            break
        say("请输入 1 或 2。")
    if not choice:
        raise AssetError("用户跳过 Google 安装包获取；未执行本次补装。")
    if choice == "1":
        cache = Path(root) / "cache/gms"
        cache.mkdir(parents=True, exist_ok=True)
        for entry in needed:
            temp = None
            try:
                with tempfile.NamedTemporaryFile(dir=cache, prefix="download-", suffix=".zip", delete=False) as out:
                    temp = Path(out.name)
                download_archive(entry, temp, proxy)
                if entry["file"] not in import_file(temp, [entry], root):
                    raise AssetError("附件中没有匹配固定 SHA-256 的目标 APK。")
                say("  校验通过。")
            except (AssetError, OSError, KeyError, ValueError) as exc:
                say("自动下载未完成：" + (str(exc) if isinstance(exc, AssetError) else "下载清单或本地文件异常。"))
                break
            finally:
                if temp is not None:
                    temp.unlink(missing_ok=True)
        needed = [e for e in entries if not cached(root, e)]
        if not needed:
            return
    say("下载页面：" + RELEASE_PAGE)
    answer = ask("按回车打开仓库下载页面，然后下载 Google 离线组件包；输入 0 跳过补装：")
    if answer == "0":
        raise AssetError("用户跳过 Google 安装包获取；未执行本次补装。")
    try:
        if not webbrowser.open(RELEASE_PAGE):
            say("浏览器未能自动打开，请复制上方地址。")
    except Exception:
        say("浏览器未能自动打开，请复制上方地址。")
    while needed:
        say("仍需：" + "、".join(e["file"] for e in needed))
        value = ask("粘贴已下载 ZIP / 文件夹 / APK 路径（支持带引号；多个路径用分号分隔；留空跳过）：")
        if not value:
            raise AssetError("安装包未补齐，用户跳过本次 Google 补装。")
        try:
            imported = import_paths(value, needed, root)
            say("已识别并校验：" + "、".join(sorted(imported)) if imported else "没有找到匹配的安装包；请检查版本、文件完整性和路径。")
        except AssetError as exc:
            say(str(exc))
        needed = [e for e in entries if not cached(root, e)]
