"""Local-only acceptance. Run after setup_tool.py with tests/fixture.yaml.

Requires both test APKs already installed; never targets a physical device.
"""
import http.client
import http.server
import json
import re
from pathlib import Path
import sys
import subprocess
import threading
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import setup_tool as s
from local_fixture import Proxy, Direct


def main():
    adb = s.Adb(s.find_adb(), "emulator-5580")
    assert adb.shell("getprop", "ro.kernel.qemu") == "1"
    assert adb.shell("settings", "get", "global", "airplane_mode_on") == "1"
    assert "Active default network: none" in adb.shell("dumpsys", "connectivity")
    assert adb.shell("settings", "get", "global", "http_proxy") in ("null", ":0")
    probe = "com.google.androidsetupprobe"
    excluded = "test.androidsetup.excluded"
    assert {probe, excluded} <= adb.packages()
    assert s.choose_whitelist({probe, excluded}, set()) == [probe]
    servers, reverse, forward = [], [], None
    ui = s.UI(adb)
    evidence = {"guest_airplane_mode": True, "guest_default_network_before": "none",
                "host_proxy_used": False, "fixture_forwards_to_internet": False}
    try:
        for port, handler in ((19090, Proxy), (19091, Direct)):
            server = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)
            servers.append(server)
            threading.Thread(target=server.serve_forever, daemon=True).start()
            adb.run("reverse", "--no-rebind", f"tcp:{port}", f"tcp:{port}")
            reverse.append(port)
        ui.home()
        ui.click("Stopped", "已停止")
        ui.dump()
        # Explicit consent only on this disposable emulator, never production setup.
        if ui.find("Connection request", "连接请求") is not None:
            ui.click("OK", "确定")
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            ui.dump()
            if ui.find("Running", "运行中") is not None:
                break
            time.sleep(1)
        else:
            raise AssertionError("VPN failed to start")
        evidence["vpn_running"] = True
        diagnostics = adb.shell("dumpsys", "vpn_management")
        evidence["vpn_diagnostics"] = diagnostics
        expected_path = Path(__file__).parent / "artifacts" / "configuration.json"
        if expected_path.exists():
            expected = json.loads(expected_path.read_text(encoding="utf-8"))["expected_selected"]
            uid_text = re.search(r"Uids: <\{([^}]+)\}>", diagnostics)
            assert uid_text is not None, "VPN UID ranges unavailable"
            ranges = [(int(lo), int(hi)) for lo, hi in re.findall(r"(\d+)-(\d+)", uid_text.group(1))]
            package_uids = dict((p, int(uid)) for p, uid in re.findall(
                r"package:(\S+) uid:(\d+)", adb.shell("pm", "list", "packages", "-U", "--user", "0")))
            for package in expected:
                uid = package_uids[package]
                assert any(lo <= uid <= hi for lo, hi in ranges), "VPN configuration missing " + package
            assert not any(lo <= package_uids[excluded] <= hi for lo, hi in ranges)
            evidence["vpn_expected_packages_verified"] = len(expected)
            print(f"VPN UID coverage: {len(expected)} selected packages; excluded probe outside ranges", flush=True)
        forward = adb.run("forward", "tcp:0", "tcp:7890")
        for label, url, marker in (("rule_proxy", "http://198.51.100.1/probe", "ANDROID_SETUP_TEST_PROXY"),
                                   ("rule_direct", "http://127.0.0.1:19091/probe", "ANDROID_SETUP_TEST_DIRECT")):
            conn = http.client.HTTPConnection("127.0.0.1", int(forward), timeout=15)
            conn.request("GET", url)
            response = conn.getresponse()
            body = response.read().decode()
            conn.close()
            assert response.status == 200 and body == marker, (label, response.status, body)
            evidence[label] = body
            print(label + ": " + body, flush=True)
        for package, marker in ((probe, "ANDROID_SETUP_TEST_PROXY"), (excluded, "PROBE_BLOCKED_NO_NETWORK")):
            adb.shell("am", "force-stop", package)
            adb.shell("am", "start", "-n", package + "/test.probe.ProbeActivity")
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                ui.dump()
                if ui.find(marker) is not None:
                    break
                time.sleep(1)
            else:
                raise AssertionError("Unexpected probe result: " + package)
            evidence[package] = marker
            print(package + ": " + marker, flush=True)
            screenshot = subprocess.run([adb.exe, "-s", adb.serial, "exec-out", "screencap", "-p"],
                                        capture_output=True, check=True, timeout=20)
            image_path = Path(__file__).parent / "artifacts" / (package + ".png")
            image_path.parent.mkdir(exist_ok=True)
            image_path.write_bytes(screenshot.stdout)
    finally:
        adb.shell("am", "start", "-a", s.PACKAGE + ".action.STOP_CLASH", "-n",
                  s.PACKAGE + "/" + s.ACTIVITY + "ExternalControlActivity", check=False)
        if forward:
            adb.run("forward", "--remove", "tcp:" + forward, check=False)
        for port in reverse:
            adb.run("reverse", "--remove", f"tcp:{port}", check=False)
        for server in servers:
            server.shutdown(); server.server_close()
    for _ in range(10):
        if "Active default network: none" in adb.shell("dumpsys", "connectivity"):
            break
        time.sleep(.5)
    evidence["guest_default_network_after"] = "none" if "Active default network: none" in adb.shell("dumpsys", "connectivity") else "unexpected"
    assert evidence["guest_default_network_after"] == "none"
    out = Path(__file__).parent / "artifacts" / "acceptance.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Acceptance passed: " + str(out), flush=True)


if __name__ == "__main__":
    main()
