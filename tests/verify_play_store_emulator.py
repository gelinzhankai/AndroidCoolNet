"""Read-only package checks and an opt-in launch on the isolated shared emulator."""
import json
from pathlib import Path
import re
import setup_tool as s

ROOT = Path(__file__).resolve().parents[1]
adb = s.Adb(r"H:\Android-Emulator\sdk\platform-tools\adb.exe", "emulator-5580")
assert "Codex_API35_Play" in adb.run("emu", "avd", "name")
assert "uid=2000(shell)" in adb.shell("id")


def isolated():
    assert adb.shell("settings", "get", "global", "airplane_mode_on") == "1"
    assert adb.shell("settings", "get", "global", "wifi_on") == "0"
    assert adb.shell("settings", "get", "global", "http_proxy") in ("null", ":0")
    assert "Active default network: none" in adb.shell("dumpsys", "connectivity")


def inventory():
    return {"packages": sorted(adb.packages()), "disabled": sorted(adb.packages("-d")),
            "google": {p: re.findall(r"(?:versionCode=\d+|versionName=[^\n]+|lastUpdateTime=[^\n]+|User 0:[^\n]+)",
                                     adb.shell("dumpsys", "package", p)) for p in s.GOOGLE_PACKAGES}}


isolated()
before = inventory()
args = ["--adb", adb.exe, "--serial", adb.serial]
assert s.main([*args, "--detect-only"]) == 0
assert inventory() == before
try:
    assert s.main([*args, "--open-play-store"]) == 0
    activity = adb.shell("dumpsys", "activity", "activities")
    assert re.search(r"(?:mResumedActivity|topResumedActivity)[:=][^\n]*com\.android\.vending/", activity)
    assert inventory() == before
    isolated()
    evidence = {"api": 35, "serial": adb.serial, "root": False, "external_network": False,
                "play_store_resumed": True, "package_versions_and_states_unchanged": True,
                "system_app": "com.android.vending" in adb.packages("-s")}
    (ROOT / "tests/artifacts").mkdir(exist_ok=True)
    (ROOT / "tests/artifacts/play-store.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print("PASS: system Play Store resumed; Google versions/states unchanged; no external network.")
finally:
    adb.shell("input", "keyevent", "KEYCODE_HOME")
