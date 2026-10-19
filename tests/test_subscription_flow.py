import contextlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("setup_subscription_test", ROOT / "setup_tool.py")
s = importlib.util.module_from_spec(spec)
spec.loader.exec_module(s)
VALID = b'proxies: [{name: local, type: http, server: 127.0.0.1, port: 19090}]'


class SubscriptionFlowTests(unittest.TestCase):
    def run_main(self, entered, payload=VALID, download_error=None, local_bad=False):
        with tempfile.TemporaryDirectory() as tmp, contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.object(s, "ROOT", Path(tmp)))
            prompt = stack.enter_context(mock.patch("builtins.input", return_value=entered))
            fetch = stack.enter_context(mock.patch.object(s, "fetch", return_value=payload, side_effect=download_error))
            stack.enter_context(mock.patch.object(s, "find_adb", return_value="not-a-real-adb"))
            stack.enter_context(mock.patch.object(s, "select_device", return_value="mock-device"))
            adb = stack.enter_context(mock.patch.object(s, "Adb")).return_value
            adb.network_candidates.return_value = (["com.google.android.gms"], [])
            stack.enter_context(mock.patch.object(s, "inspect_device", return_value=(
                {"model":"test", "android":"15", "api":35, "abis":["arm64-v8a"], "gms":{}}, {"com.google.android.gms"})))
            stack.enter_context(mock.patch.object(s, "provision_google", return_value={"complete": True}))
            install = stack.enter_context(mock.patch.object(s, "install_client", return_value="installed"))
            ui = stack.enter_context(mock.patch.object(s, "UI")).return_value
            ui.configure_whitelist.return_value = (["com.google.android.gms"], [])
            ui.activate_or_import.return_value = "imported"
            serve = stack.enter_context(mock.patch.object(s, "serve_profile"))
            serve.return_value.__enter__.return_value = "http://127.0.0.1/local-only"
            output = stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
            args = ["--allowlist", str(ROOT/"config/apps.json"), "--rules", str(ROOT/"config/rules.json"),
                    "--profile-settings", str(ROOT/"config/profile.yaml")]
            if local_bad:
                path = Path(tmp)/"invalid.yaml"
                path.write_text("proxies: [", encoding="utf-8")
                args.extend(["--profile-file", str(path)])
            self.assertEqual(s.main(args), 0)
            install.assert_called_once()
            ui.configure_whitelist.assert_called_once()
            report = next(r for p in (Path(tmp)/"reports").glob("*.json")
                          if "subscription_status" in (r := json.loads(p.read_text(encoding="utf-8"))))
            if report["profile_status"] == "skipped":
                ui.activate_or_import.assert_not_called()
                serve.assert_not_called()
                self.assertIsNone(report["profile"])
                self.assertNotIn("配置已导入并激活", output.getvalue())
            else:
                ui.activate_or_import.assert_called_once()
                serve.assert_called_once()
            self.assertNotIn("private-subscription-token", json.dumps(report))
            self.assertNotIn("private-subscription-token", output.getvalue())
            return report, prompt, fetch

    def test_blank_visible_input_keeps_install_and_whitelist(self):
        report, prompt, fetch = self.run_main("  ")
        self.assertEqual(report["subscription_status"], "skipped_empty")
        self.assertIn("明文显示", prompt.call_args.args[0])
        fetch.assert_not_called()

    def test_invalid_yaml_keeps_install_and_existing_profile(self):
        report, _, _ = self.run_main("https://example.test/private-subscription-token", b"<html>expired</html>")
        self.assertEqual(report["subscription_status"], "skipped_invalid")

    def test_download_failure_skips_without_echoing_exception(self):
        report, _, _ = self.run_main("https://example.test/private-subscription-token",
                                    download_error=s.SetupError("private-subscription-token"))
        self.assertEqual(report["subscription_status"], "skipped_download_error")

    def test_malformed_url_skips(self):
        report, _, _ = self.run_main("https://[", download_error=ValueError("Invalid IPv6 URL"))
        self.assertEqual(report["subscription_status"], "skipped_download_error")

    def test_invalid_local_yaml_skips(self):
        report, prompt, fetch = self.run_main("unused", local_bad=True)
        self.assertEqual(report["subscription_status"], "skipped_invalid")
        prompt.assert_not_called()
        fetch.assert_not_called()

    def test_valid_subscription_still_imports_and_reports_success(self):
        report, _, _ = self.run_main("https://example.test/private-subscription-token")
        self.assertEqual(report["subscription_status"], "parsed")
        self.assertEqual(report["profile_status"], "imported")

    def test_profile_settings_reach_generated_yaml(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)/"profile.yaml"
            p.write_text('port: 8080\nsocks-port: null\nmixed-port: 7891\nipv6: true\nallow-lan: false\nauthentication: ["demo:example"]\n', encoding="utf-8")
            settings = s.load_profile_settings(p)
            profile = s.yaml.safe_load(s.make_profile(s.extract_proxies(VALID), ["MATCH,PROXY"], settings))
            self.assertEqual(profile["port"], 8080)
            self.assertEqual(profile["mixed-port"], 7891)
            self.assertTrue(profile["ipv6"])
            self.assertNotIn("socks-port", profile)
            self.assertEqual(profile["authentication"], ["demo:example"])

    def test_invalid_profile_settings_do_not_silently_apply(self):
        for data in ('port: -1', 'ipv6: "false"', 'proxies: []', 'external-controller: "127.0.0.1:9090"'):
            with self.subTest(data=data), tempfile.TemporaryDirectory() as tmp:
                p = Path(tmp)/"profile.yaml"
                p.write_text(data, encoding="utf-8")
                with self.assertRaises(s.SetupError):
                    s.load_profile_settings(p)


if __name__ == "__main__":
    unittest.main()
