"""Maintainer-only: pin downloaded, signature-verified original app bundles and split metadata."""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
BT = Path(r"C:\Android\Sdk\build-tools\35.0.0")
JAVA = Path(r"C:\Program Files\Microsoft\jdk-21.0.9.10-hotspot\bin\java.exe")
SAMPLES = [
    dict(id="chatgpt", name="ChatGPT", package="com.openai.chatgpt", file="chatgpt-1.2026.286.apkm",
         source="https://www.apkmirror.com/apk/openai/chatgpt/chatgpt-1-2026-286-release/chatgpt-1-2026-286-android-apk-download/",
         provider="apkmirror", anchor_algorithm="SHA-256",
         anchor="b24f4bfbb3cf293f938703b9d87027c1102cc36dc4fa206910e08927db40473c",
         archive_sha256="f7c63001f38d916f643def5df7fb3b9cf8155f746221ba6221223c70f9528414"),
    dict(id="claude", name="Claude", package="com.anthropic.claude", file="claude-1.261020.20.xapk",
         source="https://claude.en.uptodown.com/android/download/1229822033-x",
         provider="uptodown", app_id="1000217326", file_id="1229822033", anchor_algorithm="MD5",
         anchor="2e746b8a2e01023c55ed06b2945690c6",
         archive_sha256="897a6aef6b4d9dda004d25a108ec3893c96e64d2583daa31a3bf502e0ac0e6db"),
]
DPI = {"ldpi": 120, "mdpi": 160, "tvdpi": 213, "hdpi": 240, "xhdpi": 320, "xxhdpi": 480, "xxxhdpi": 640}


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def run(*args):
    return subprocess.check_output(list(map(str, args)), encoding="utf-8", errors="replace")


entries = []
for spec in SAMPLES:
    path = ROOT / "cache/ai" / spec["file"]
    assert sha(path) == spec["archive_sha256"]
    with tempfile.TemporaryDirectory(prefix="acn-app-review-") as folder, zipfile.ZipFile(path) as archive:
        names = [n for n in archive.namelist() if n.endswith(".apk")]
        assert names and len(names) == len(set(names))
        assert all(Path(n).name == n and not any(c in n for c in "\\/:") for n in names)
        files = []
        for name in names:
            target = Path(folder) / name
            target.write_bytes(archive.read(name))
            files.append(target)
        verified = run(JAVA, "-cp", BT / "lib/apksigner.jar", ROOT / "tests/VerifyAppSet.java",
                       spec["anchor_algorithm"], spec["anchor"], *files)
        certs = {line.split()[1] for line in verified.splitlines()}
        assert len(certs) == 1
        parts, bases = [], []
        for apk in files:
            badge = run(BT / "aapt.exe", "dump", "badging", apk)
            pkg, code, version = re.search(r"package: name='([^']+)' versionCode='(\d+)' versionName='([^']*)'", badge).groups()
            assert pkg == spec["package"]
            split = re.search(r"\bsplit='([^']+)'", badge.splitlines()[0])
            part = dict(file=apk.name, bytes=apk.stat().st_size, sha256=sha(apk), split=split[1] if split else "")
            if not split:
                bases.append(part)
                spec.update(version_name=version, version_code=int(code), min_sdk=int(re.search(r"sdkVersion:'(\d+)'", badge)[1]))
                assert not re.findall(r"^uses-library:'([^']+)'", badge, re.M)
                part["kind"] = "base"
            else:
                value = split[1].removeprefix("config.")
                native = re.findall(r"^native-code: (.+)$", badge, re.M)
                if native:
                    abis = re.findall(r"'([^']+)'", native[0])
                    assert len(abis) == 1
                    part.update(kind="abi", abi=abis[0])
                elif value in DPI:
                    part.update(kind="dpi", dpi=DPI[value])
                else:
                    assert re.fullmatch(r"[a-z]{2,3}", value), "Review new feature/config splits explicitly"
                    part.update(kind="language", language=value)
            part["version_code"] = int(code)
            parts.append(part)
        assert len(bases) == 1 and all(p["version_code"] == spec["version_code"] for p in parts)
        entry = {k: v for k, v in spec.items() if not k.startswith("anchor")}
        entry.update(bytes=path.stat().st_size, certificate_sha256=next(iter(certs)), parts=parts,
                     supported_api_min=35, supported_api_max=37,
                     validation="Every APK signature verified with Android apksig; signer matched mirror metadata; login/network not verified")
        entries.append(entry)
        print(entry["id"], len(parts), entry["certificate_sha256"], entry["bytes"], flush=True)
(ROOT / "config/ai-apps.json").write_text(json.dumps({"schema": 1, "apps": entries}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
