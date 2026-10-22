import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import xml.etree.ElementTree as ET

import setup_tool as s


class ClipboardConfigurationTests(unittest.TestCase):
    def test_existing_helper_is_never_replaced_or_removed(self):
        adb = mock.Mock()
        adb.packages.return_value = {s.ClipboardBridge.package}
        bridge = s.ClipboardBridge(adb)
        with self.assertRaises(s.SetupError):
            bridge.install()
        bridge.cleanup()
        adb.run.assert_not_called()

    def test_corrupt_helper_is_never_installed(self):
        with tempfile.TemporaryDirectory() as temp, mock.patch.object(s, "ROOT", Path(temp)):
            (Path(temp) / "config").mkdir()
            (Path(temp) / "cache").mkdir()
            (Path(temp) / "cache/androidcoolnet-clipboard.apk").write_bytes(b"corrupt")
            (Path(temp) / "config/clipboard-helper.json").write_text(json.dumps({
                "package": s.ClipboardBridge.package, "sha256": "0" * 64}))
            adb = mock.Mock()
            adb.packages.return_value = set()
            with self.assertRaises(s.SetupError):
                s.ClipboardBridge(adb).install()
            adb.run.assert_not_called()

    def test_uninstall_failure_is_reported_without_masking_original_error(self):
        bridge = s.ClipboardBridge(mock.Mock())
        bridge.installed_here = True
        bridge.adb.run.side_effect = s.SetupError("disconnected")
        with mock.patch.object(s, "say"):
            bridge.cleanup()
        self.assertEqual(bridge.cleanup_status, "failed")

    def test_export_rejects_stale_clipboard_instead_of_confirming_import(self):
        clipboard = mock.Mock()
        clipboard.read.return_value = "ACN_EXPORT:unchanged"
        ui = s.UI(mock.Mock(), clipboard)
        ui.clipboard_menu = mock.Mock()
        with self.assertRaises(s.SetupError):
            ui.export_whitelist()
        clipboard.write.assert_called_once()

    def test_export_exact_packages_with_empty_list_supported(self):
        clipboard = mock.Mock()
        ui = s.UI(mock.Mock(), clipboard)
        ui.clipboard_menu = mock.Mock()
        for text, expected in [("", set()), ("com.google.android.gms\ncom.android.vending", {
                "com.google.android.gms", "com.android.vending"})]:
            clipboard.read.return_value = text
            self.assertEqual(ui.export_whitelist(), expected)

    def test_override_is_not_verified_from_a_different_rows_summary(self):
        ui = s.UI(mock.Mock())
        ui.root = ET.fromstring('''<hierarchy><node>
          <node clickable="true"><node text="IPv6"/><node text="Do not modify"/></node>
          <node clickable="true"><node text="Other"/><node text="Disabled"/></node>
        </node></hierarchy>''')
        ui.seek_preference = mock.Mock(return_value=list(ui.root.iter("node"))[2])
        with self.assertRaises(s.SetupError):
            ui.override_choice(("IPv6",), ("Disabled",), verify=True)
        ui.adb.shell.assert_not_called()

    def test_override_server_configuration_validates_before_device_changes(self):
        for document, valid in [
            ('nameserver: ["8.8.8.8", "1.1.1.1"]', True),
            ('nameserver: ["2606:4700:4700::1111"]', True),
            ('nameserver: []', False), ('nameserver: ["8.8.8.8", "8.8.8.8"]', False),
            ('nameserver: ["8.8.8.8; reboot"]', False),
            ('nameserver: [8]', False), ('nameserver: ["8.8.8.8"]\nsecret: something', False),
        ]:
            with self.subTest(document=document), tempfile.TemporaryDirectory() as temp:
                path = Path(temp) / "override.yaml"
                path.write_text(document)
                if valid:
                    self.assertTrue(s.load_override_settings(path))
                else:
                    with self.assertRaises(s.SetupError):
                        s.load_override_settings(path)

    def test_paste_corruption_stops_instead_of_accepting_wrong_text(self):
        ui = s.UI(mock.Mock(), mock.Mock())
        ui.dump = mock.Mock()
        ui.tap = mock.Mock()
        ui.find = mock.Mock(side_effect=[ET.Element("node", text="Name Server"),
                                        ET.Element("node", text="Name Server"),
                                        ET.Element("node", text="8 .8.8.8")])
        with self.assertRaises(s.SetupError):
            ui.replace_text("8.8.8.8")
        ui.clipboard.write.assert_called_once_with("8.8.8.8")
        ui.adb.shell.assert_any_call("input", "keyevent", "KEYCODE_PASTE")
        self.assertFalse(any(call.args[:2] == ("input", "text") for call in ui.adb.shell.call_args_list))


if __name__ == "__main__":
    unittest.main()
