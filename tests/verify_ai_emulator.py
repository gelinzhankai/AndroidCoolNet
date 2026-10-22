"""Install reviewed bundles offline, verify repeat-run preservation, then remove only test apps."""
import json
from pathlib import Path
import re
import shutil
import tempfile
import setup_tool as s

ROOT = Path(__file__).resolve().parents[1]
adb = s.Adb(r"H:\Android-Emulator\sdk\platform-tools\adb.exe", "emulator-5580")
assert "Codex_API35_Play" in adb.run("emu", "avd", "name")
assert "uid=2000(shell)" in adb.shell("id")
packages = {"com.openai.chatgpt", "com.anthropic.claude"}


def isolated():
    assert adb.shell("settings", "get", "global", "airplane_mode_on") == "1"
    assert adb.shell("settings", "get", "global", "wifi_on") == "0"
    assert adb.shell("settings", "get", "global", "http_proxy") in ("null", ":0")
    assert "Active default network: none" in adb.shell("dumpsys", "connectivity")


def state(package):
    return re.findall(r"(?:versionCode=\d+|versionName=[^\n]+|lastUpdateTime=[^\n]+|User 0:[^\n]+)",
                      adb.shell("dumpsys", "package", package))


isolated()
assert not packages & adb.packages("-u"), "Test apps already exist; do not replace them."
before = {"packages": adb.packages(), "disabled": adb.packages("-d"),
          "google": {p: state(p) for p in s.GOOGLE_PACKAGES}}
catalog = json.loads((ROOT / "config/ai-apps.json").read_text(encoding="utf-8"))
original_root = s.ROOT
try:
    with tempfile.TemporaryDirectory(prefix="acn-ai-test-") as folder:
        s.ROOT = Path(folder)
        (s.ROOT / "config").mkdir()
        shutil.copyfile(ROOT / "config/ai-apps.json", s.ROOT / "config/ai-apps.json")
        args = ["--adb", adb.exe, "--serial", adb.serial, "--apps-only", "--ai-apps", "both"]
        for entry in catalog["apps"]:
            args += ["--app-file", str(ROOT / "cache/ai" / entry["file"])]
        assert s.main(args) == 0
        first = json.loads(next((s.ROOT / "reports").glob("*.json")).read_text(encoding="utf-8"))["ai_apps"]
        assert all(r["status"] == "installed" for r in first["apps"].values())
        assert adb.packages() == before["packages"] | packages
        installed_states = {p: state(p) for p in packages}
        assert s.main(args) == 0
        latest = max((s.ROOT / "reports").glob("*.json"), key=lambda p: p.stat().st_mtime_ns)
        second = json.loads(latest.read_text(encoding="utf-8"))["ai_apps"]
        assert all(r["status"] == "already_installed" for r in second["apps"].values())
        assert installed_states == {p: state(p) for p in packages}
        device, installed = s.inspect_device(adb)
        template = json.loads((ROOT / "config/apps.json").read_text(encoding="utf-8"))["apps"]
        desired = s.choose_whitelist(installed, {a["package"] for a in template})
        eligible, _ = adb.network_candidates(desired)
        assert packages <= set(eligible)
        evidence = {"api": device["api"], "abis": device["abis"], "root": False,
                    "external_network": False, "login_verified": False, "first_run": first,
                    "second_run": second, "whitelist_candidates_include_both": True}
finally:
    s.ROOT = original_root
    for package in sorted(packages & adb.packages()):
        assert adb.run("uninstall", package) == "Success"
    assert adb.packages() == before["packages"]
    assert adb.packages("-d") == before["disabled"]
    assert {p: state(p) for p in s.GOOGLE_PACKAGES} == before["google"]
    isolated()

(ROOT / "tests/artifacts").mkdir(exist_ok=True)
evidence["restored_packages_google_and_disabled_states"] = True
(ROOT / "tests/artifacts/ai-apps.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
print("PASS: both original split apps installed, repeat run preserved them, whitelist candidates include both; cleaned up offline.")
