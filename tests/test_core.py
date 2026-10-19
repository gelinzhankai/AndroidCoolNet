import importlib.util
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("setup_tool", ROOT / "setup_tool.py")
s = importlib.util.module_from_spec(spec)
spec.loader.exec_module(s)


class CoreTests(unittest.TestCase):
    def test_google_system_packages_are_dynamic(self):
        installed = {"com.google.android.gms", "vendor.Google.overlay", "com.android.vending",
                     "com.anthropic.claude", "com.example.other"}
        self.assertEqual(s.choose_whitelist(installed, {"com.anthropic.claude"}),
                         sorted(installed - {"com.example.other"}))

    def test_empty_or_non_clash_subscription_fails(self):
        for raw in (b"", b"<html>expired</html>", b"proxies: []", b"proxy-providers: {}", b"a: ["):
            with self.subTest(raw=raw), self.assertRaises(s.SetupError):
                s.extract_proxies(raw)

    def test_duplicate_or_reserved_names_fail(self):
        node = {"name":"PROXY", "type":"http", "server":"example.test", "port":443}
        with self.assertRaises(s.SetupError):
            s.extract_proxies(s.yaml.safe_dump({"proxies":[node]}))
        node["name"] = "node"
        with self.assertRaises(s.SetupError):
            s.extract_proxies(s.yaml.safe_dump({"proxies":[node, node]}))

    def test_foreign_subscription_rules_and_controller_not_inherited(self):
        data = b'proxies: [{name: node, type: http, server: example.test, port: 443}]\nexternal-controller: 0.0.0.0:9090\nrules: ["MATCH,DIRECT"]'
        profile = s.yaml.safe_load(s.make_profile(s.extract_proxies(data), ["MATCH,PROXY"]))
        self.assertEqual(profile["rules"], ["MATCH,PROXY"])
        self.assertNotIn("external-controller", profile)
        self.assertFalse(profile["allow-lan"])
        self.assertNotIn("DIRECT", profile["proxy-groups"][0]["proxies"])

    def test_credentials_and_unicode_survive_yaml_roundtrip(self):
        node = {"name":"日本: 节点", "type":"http", "server":"example.test", "port":443,
                "username":"test", "password":"a:#&'\""}
        payload = s.make_profile(s.extract_proxies(s.yaml.safe_dump({"proxies":[node]})), ["MATCH,PROXY"])
        self.assertEqual(s.yaml.safe_load(payload)["proxies"], [node])

    def test_network_filter_preserves_low_system_uid(self):
        class Fake(s.Adb):
            def __init__(self): pass
            def shell(self, *args):
                return "  Package [com.google.system] (a):\n    appId=1000\n  Package [com.google.overlay] (b):\n    appId=10001\n  Package [com.google.app] (c):\n    appId=10002\n    android.permission.INTERNET\n"
        yes, no = Fake().network_candidates(["com.google.system", "com.google.overlay", "com.google.app"])
        self.assertEqual(yes, ["com.google.system", "com.google.app"])
        self.assertEqual(no, ["com.google.overlay"])

    def test_shared_uid_google_services_are_not_dropped(self):
        class Fake(s.Adb):
            def __init__(self): pass
            def shell(self, *args):
                return "  Package [com.google.android.gms] (a):\n    appId=10144\n    sharedUser=SharedUserSetting{abc com.google.uid.shared/10144}\n  Package [com.google.updated] (b):\n    appId=10200\n    android.permission.INTERNET\nHidden system packages:\n  Package [com.google.updated] (c):\n    appId=10200\n"
        desired = ["com.google.android.gms", "com.google.updated"]
        self.assertEqual(Fake().network_candidates(desired), (desired, []))


if __name__ == "__main__":
    unittest.main()
