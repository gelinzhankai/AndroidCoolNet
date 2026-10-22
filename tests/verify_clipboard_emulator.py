"""Full v0.5.0 workflow on the isolated shared emulator; never targets a phone."""
import json
import re
from pathlib import Path
import sys
import tempfile
import time
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import setup_tool as s


def main():
    skip_subscription = "--skip-subscription" in sys.argv
    adb_path = r"H:\Android-Emulator\sdk\platform-tools\adb.exe"
    adb = s.Adb(adb_path, "emulator-5580")
    assert adb.shell("getprop", "ro.kernel.qemu") == "1"
    assert "uid=2000(shell)" in adb.shell("id")
    assert adb.shell("settings", "get", "global", "airplane_mode_on") == "1"
    assert adb.shell("settings", "get", "global", "http_proxy") in ("null", ":0")
    assert "Active default network: none" in adb.shell("dumpsys", "connectivity")
    before = adb.packages()
    assert s.ClipboardBridge.package not in adb.packages("-u")
    ui = s.UI(adb)
    ui.home()
    previous_profile = next((match.group() for n in ui.nodes()
                             if (match := re.match(r"AndroidSetup-[0-9a-f]{10}", n.get("text", "")))), None)
    existing_reports = set((s.ROOT / "reports").glob("*.json"))
    original_shell = s.Adb.shell

    def checked_shell(self, *args, **kwargs):
        assert args[:2] != ("input", "text"), "Keyboard text injection must not be used"
        return original_shell(self, *args, **kwargs)

    s.Adb.shell = checked_shell
    with tempfile.TemporaryDirectory() as temp:
        fixture = Path(temp) / "local.yaml"
        fixture.write_text("proxies: [{name: CLIPBOARD-TEST-" + str(time.time_ns()) +
                           ", type: http, server: 127.0.0.1, port: 19090}]", encoding="utf-8")
        override = Path(temp) / "override.yaml"
        override.write_text('nameserver: ["8.8.8.8", "1.1.1.1"]', encoding="utf-8")
        arguments = ["--serial", "emulator-5580", "--adb", adb_path, "--skip-gms",
                     "--override-settings", str(override)]
        if not skip_subscription:
            arguments += ["--profile-file", str(fixture)]
        with mock.patch("builtins.input", return_value=""):
            assert s.main(arguments) == 0
    reports = set((s.ROOT / "reports").glob("*.json")) - existing_reports
    report = next(data for path in reports if "profile_status" in
                  (data := json.loads(path.read_text(encoding="utf-8"))))
    assert report["profile_status"] == ("skipped" if skip_subscription else "imported")
    assert report["override"]["status"] == "verified"
    assert report["override"]["dns"]["nameserver"] == ["8.8.8.8", "1.1.1.1"]
    assert report["clipboard_helper_cleanup"] == "removed"
    assert {"com.google.android.gms", "com.google.android.gsf", "com.android.vending"} <= set(report["whitelist_selected"])
    assert not report["not_selectable_in_cmfa"]
    assert adb.packages() == before
    assert s.ClipboardBridge.package not in adb.packages("-u")
    assert "Active default network: none" in adb.shell("dumpsys", "connectivity")
    assert adb.run("reverse", "--list") == ""
    # Remove only the newly generated non-network test profile; keep the pre-existing fixture.
    if not skip_subscription:
        ui.home()
        ui.click("Profiles", "Profile", "配置")
        ui.profile_menu(report["profile"])
        ui.click("Delete", "删除")
        ui.dump()
        if ui.find("OK", "确定", "确认") is not None:
            ui.click("OK", "确定", "确认")
        if previous_profile is not None:
            previous = ui.find_profile(previous_profile)
            assert previous is not None, "The pre-existing local fixture must still be present"
            ui.tap(previous)
        ui.back()
    else:
        ui.home()
        assert previous_profile is None or any(previous_profile in n.get("text", "") for n in ui.nodes())
    output = s.ROOT / "tests/artifacts/clipboard-override.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({"selected": len(report["whitelist_selected"]),
                                 "override": report["override"], "helper_removed": True,
                                 "shell_uid": 2000, "keyboard_text_injection": False,
                                 "external_network": False,
                                 "subscription_status": report["subscription_status"]}, indent=2), encoding="utf-8")
    print("PASS: full workflow (subscription " + report["profile_status"] + "), whitelist re-export, two DNS servers, persisted override, cleanup; no input text/root/Internet")


if __name__ == "__main__":
    main()
