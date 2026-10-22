import contextlib
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import zipfile
import ai_apps as a

CATALOG = json.loads((Path(__file__).resolve().parents[1] / "config/ai-apps.json").read_text())["apps"]
DEVICE = {"api": 35, "abis": ["arm64-v8a", "armeabi-v7a"], "preview_sdk": 0}


class AiAppsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "config").mkdir()
        self.bundle = self.root / "original.xapk"
        with zipfile.ZipFile(self.bundle, "w") as z:
            z.writestr("base.apk", b"original-fixture")
        self.entry = dict(id="claude", name="Claude", package="com.anthropic.claude", file="claude.xapk",
                          provider="uptodown", source="https://claude.en.uptodown.com/android/download/1229822033-x",
                          version_name="fixture", version_code=1, bytes=self.bundle.stat().st_size,
                          archive_sha256=a.sha(self.bundle), supported_api_min=35, supported_api_max=37,
                          min_sdk=32, parts=[dict(file="base.apk", kind="base", bytes=16,
                                                sha256=hashlib.sha256(b"original-fixture").hexdigest())])
        (self.root / "config/ai-apps.json").write_text(json.dumps({"apps": [self.entry]}))
        self.adb = mock.Mock()
        self.installed = set()
        self.adb.packages.side_effect = lambda *flags: set(self.installed)
        self.adb.shell.return_value = "Physical density: 320\nOverride density: 400"
        def install(*args, **kwargs):
            self.installed.add("com.anthropic.claude")
            return "Success"
        self.adb.run.side_effect = install
        self.output = io.StringIO()
        self.addCleanup(mock.patch.stopall)
        mock.patch.object(a, "say").start()

    def provision(self, **kwargs):
        with contextlib.redirect_stdout(self.output):
            return a.provision_ai_apps(self.adb, DEVICE, self.root, selection="claude", files=[str(self.bundle)], **kwargs)

    def test_installs_verified_set_with_explicit_no_replace(self):
        result = self.provision()
        self.assertEqual(result["apps"]["claude"]["status"], "installed")
        args = self.adb.run.call_args.args
        self.assertEqual(args[:5], ("install-multiple", "--no-streaming", "-R", "--user", "0"))
        self.assertNotIn("-r", args)

    def test_installed_app_skips_every_download_and_install(self):
        self.installed.add("com.anthropic.claude")
        with mock.patch.object(a, "acquire") as acquire:
            self.assertEqual(self.provision()["apps"]["claude"]["status"], "already_installed")
        acquire.assert_not_called()
        self.adb.run.assert_not_called()
        self.adb.shell.assert_not_called()

    def test_another_users_app_is_not_replaced(self):
        self.adb.packages.side_effect = lambda *flags: {"com.anthropic.claude"} if flags else set()
        self.assertFalse(self.provision()["complete"])
        self.adb.run.assert_not_called()

    def test_race_prevents_replacement(self):
        self.adb.packages.side_effect = [set(), set(), {"com.anthropic.claude"}]
        self.assertFalse(self.provision()["complete"])
        self.adb.run.assert_not_called()

    def test_store_installer_and_modified_archive_are_rejected(self):
        self.bundle.write_bytes(b"not-claude-store-installer")
        result = self.provision()
        self.assertFalse(result["complete"])
        self.adb.run.assert_not_called()

    def test_install_failure_is_partial_not_exception(self):
        self.adb.run.side_effect = None
        self.adb.run.return_value = "Failure [INSTALL_FAILED_USER_RESTRICTED]"
        result = self.provision()
        self.assertFalse(result["complete"])
        self.assertIn("INSTALL_FAILED_USER_RESTRICTED", result["apps"]["claude"]["reason"])

    def test_success_without_package_is_not_success(self):
        self.adb.run.side_effect = None
        self.adb.run.return_value = "Success"
        self.assertFalse(self.provision()["complete"])

    def test_download_failure_falls_back_to_manual_original(self):
        with mock.patch.object(a, "download_bundle", side_effect=OSError("temporary-url-secret")), \
             mock.patch.object(a.webbrowser, "open") as opened, \
             mock.patch("builtins.input", side_effect=["1", "", str(self.bundle)]):
            result = a.acquire(self.entry, self.root)
        self.assertTrue(a.cached(result, self.entry))
        opened.assert_called_once_with(self.entry["source"])

    def test_manual_wrong_file_can_retry(self):
        wrong = self.root / "installer.apk"
        wrong.write_bytes(b"installer")
        with mock.patch.object(a.webbrowser, "open"), mock.patch("builtins.input", side_effect=["2", "", str(wrong), str(self.bundle)]):
            self.assertTrue(a.cached(a.acquire(self.entry, self.root), self.entry))

    def test_skip_and_eof_do_not_install(self):
        for answer in ("", "0"):
            with mock.patch("builtins.input", return_value=answer):
                result = a.provision_ai_apps(self.adb, DEVICE, self.root)
            self.assertEqual(result["selected"], [])
        with mock.patch("builtins.input", side_effect=EOFError):
            self.assertIsNone(a.acquire(self.entry, self.root))
        self.adb.run.assert_not_called()

    def test_actual_catalog_selects_one_abi_and_density_and_all_languages(self):
        for entry in CATALOG:
            selected = a.select_parts(entry, DEVICE, 420)
            self.assertEqual([p["abi"] for p in selected if p["kind"] == "abi"], ["arm64-v8a"])
            self.assertEqual([p["dpi"] for p in selected if p["kind"] == "dpi"], [480])
            self.assertTrue(any(p.get("language") == "zh" for p in selected))
            self.assertEqual(sum(p["kind"] == "base" for p in selected), 1)

    def test_unsupported_arch_sdk_preview_stop_before_acquire(self):
        for device in ({**DEVICE, "abis": ["riscv64"]}, {**DEVICE, "api": 34}, {**DEVICE, "preview_sdk": 1}):
            with self.assertRaises(a.AppError):
                a.select_parts(CATALOG[0], device, 320)

    def test_archive_pin_checked_again_before_extract(self):
        self.bundle.write_bytes(b"changed-after-copy")
        with self.assertRaises(a.AppError):
            a.extract_verified(self.bundle, self.entry, self.entry["parts"], self.root)

    def test_apk_hash_checked_before_install(self):
        self.entry["parts"][0]["sha256"] = "0" * 64
        with self.assertRaises(a.AppError):
            a.extract_verified(self.bundle, self.entry, self.entry["parts"], self.root)

    def test_unreviewed_extra_apk_rejected_even_with_archive_pin(self):
        with zipfile.ZipFile(self.bundle, "a") as z:
            z.writestr("store.apk", b"installer")
        self.entry.update(bytes=self.bundle.stat().st_size, archive_sha256=a.sha(self.bundle))
        with self.assertRaises(a.AppError):
            a.extract_verified(self.bundle, self.entry, self.entry["parts"], self.root)

    def test_https_source_allowlist_cannot_redirect_to_arbitrary_host(self):
        for url in ("http://www.apkmirror.com/", "https://apkmirror.com.evil.test/", "https://127.0.0.1/", "https://user:pass@dw.uptodown.com/", "https://dw.uptodown.com:8080/"):
            with self.assertRaises(a.AppError):
                a.validate_url(url)

    def test_uptodown_requires_original_file_response(self):
        entry = {**self.entry, "app_id": "1000217326", "file_id": "1229822033"}
        response = mock.MagicMock()
        response.__enter__.return_value = response
        response.geturl.return_value = entry["source"]
        response.read.return_value = b'{"success":1,"data":{"downloadURL":"https://dw.uptodown.com/original"}}'
        opener = mock.Mock()
        opener.open.return_value = response
        self.assertEqual(a.resolve_download(entry, opener), "https://dw.uptodown.com/original")
        response.read.return_value = b'{"success":0}'
        with self.assertRaises(a.AppError):
            a.resolve_download(entry, opener)


if __name__ == "__main__":
    unittest.main()
