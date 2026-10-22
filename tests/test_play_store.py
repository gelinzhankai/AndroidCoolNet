import contextlib
import importlib.util
import io
from pathlib import Path
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("play_store_test", ROOT / "setup_tool.py")
s = importlib.util.module_from_spec(spec)
spec.loader.exec_module(s)
PACKAGE = "com.android.vending"
COMPONENT = PACKAGE + "/com.google.android.finsky.activities.MainActivity"


class PlayStoreTests(unittest.TestCase):
    def setUp(self):
        self.adb = mock.Mock()
        self.adb.packages.return_value = {PACKAGE}
        self.adb.shell.return_value = COMPONENT
        self.device = {"model": "test", "android": "15", "api": 35,
                       "abis": ["x86_64"], "gms": {PACKAGE: "installed"}}
        self.addCleanup(mock.patch.stopall)
        mock.patch.object(s, "say").start()

    def test_installed_system_app_resolves_without_writes(self):
        result = s.inspect_play_store(self.adb, self.device)
        self.assertEqual(result["status"], "launcher_available")
        self.assertTrue(result["system_app"])
        self.assertEqual(result["component"], COMPONENT)
        self.adb.shell.assert_called_once_with(
            "cmd", "package", "resolve-activity", "--brief", "--user", "0",
            "-a", "android.intent.action.MAIN", "-c", "android.intent.category.LAUNCHER",
            "-p", PACKAGE, include_stderr=True)
        self.adb.run.assert_not_called()

    def test_non_installed_states_never_resolve_or_open(self):
        for state in ("missing", "disabled", "not_installed_for_user", "unknown"):
            with self.subTest(state=state):
                self.device["gms"][PACKAGE] = state
                result = s.inspect_play_store(self.adb, self.device)
                self.assertEqual(result["status"], state)
                self.assertEqual(s.open_play_store(self.adb, result)["launch_status"], "unavailable")
        self.adb.shell.assert_not_called()
        self.adb.run.assert_not_called()

    def test_missing_launcher_does_not_mark_package_missing(self):
        self.adb.shell.return_value = "No activity found\n"
        result = s.inspect_play_store(self.adb, self.device)
        self.assertEqual(result["status"], "no_launcher")
        self.assertEqual(result["package_state"], "installed")

    def test_invalid_resolver_output_cannot_be_launched(self):
        for output in ("", "Unknown command: resolve-activity", "android/.ResolverActivity",
                       COMPONENT + ";reboot", COMPONENT + "\n" + COMPONENT):
            with self.subTest(output=output):
                self.adb.shell.return_value = output
                result = s.inspect_play_store(self.adb, self.device)
                self.assertEqual(result["status"], "check_failed")
                self.assertIsNone(result["component"])

    def test_probe_timeout_is_reported_not_raised(self):
        self.adb.shell.side_effect = s.SetupError("timeout")
        self.assertEqual(s.inspect_play_store(self.adb, self.device)["status"], "check_failed")

    def test_launch_reports_only_request_acceptance(self):
        diagnosis = s.inspect_play_store(self.adb, self.device)
        self.adb.shell.reset_mock()
        self.adb.shell.return_value = "Starting: Intent {}\nStatus: ok\nComplete"
        result = s.open_play_store(self.adb, diagnosis)
        self.assertEqual(result["launch_status"], "request_accepted")
        self.assertEqual(diagnosis["launch_status"], "not_requested")
        self.adb.shell.assert_called_once_with(
            "am", "start", "-W", "--user", "0", "-a", "android.intent.action.MAIN",
            "-c", "android.intent.category.LAUNCHER", "-n", COMPONENT, include_stderr=True)

    def test_launch_errors_never_report_success(self):
        diagnosis = s.inspect_play_store(self.adb, self.device)
        for output in ("Status: timeout", "Error: Activity not started", "Status: ok\nSecurityException"):
            self.adb.shell.return_value = output
            self.assertEqual(s.open_play_store(self.adb, diagnosis)["launch_status"], "failed")
        self.adb.shell.side_effect = s.SetupError("timeout")
        self.assertEqual(s.open_play_store(self.adb, diagnosis)["launch_status"], "failed")

    def run_main(self, mode):
        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.object(s, "find_adb", return_value="mock-adb"))
            stack.enter_context(mock.patch.object(s, "select_device", return_value="mock-device"))
            stack.enter_context(mock.patch.object(s, "Adb", return_value=self.adb))
            stack.enter_context(mock.patch.object(s, "inspect_device", return_value=(self.device, {PACKAGE})))
            privacy = stack.enter_context(mock.patch.object(s, "optional_antifraud_removal", return_value={"status": "not_installed"}))
            google = stack.enter_context(mock.patch.object(s, "provision_google"))
            client = stack.enter_context(mock.patch.object(s, "install_client"))
            save = stack.enter_context(mock.patch.object(s, "save_report"))
            self.adb.shell.side_effect = [COMPONENT, "Status: ok"]
            self.assertEqual(s.main([mode]), 0)
            google.assert_not_called()
            client.assert_not_called()
            self.adb.run.assert_not_called()
            return save, privacy

    def test_open_mode_bypasses_installation_and_uninstall_prompt(self):
        save, privacy = self.run_main("--open-play-store")
        privacy.assert_not_called()
        report = save.call_args.args[0]
        self.assertEqual(report["play_store"]["launch_status"], "request_accepted")

    def test_detect_mode_does_not_write_or_launch(self):
        save, privacy = self.run_main("--detect-only")
        self.assertTrue(privacy.call_args.kwargs["detect_only"])
        save.assert_not_called()
        self.adb.shell.assert_called_once()

    def test_detect_and_open_flags_are_incompatible(self):
        with contextlib.redirect_stderr(io.StringIO()), mock.patch.object(s, "find_adb") as find:
            with self.assertRaises(SystemExit):
                s.main(["--detect-only", "--open-play-store"])
            find.assert_not_called()


if __name__ == "__main__":
    unittest.main()
