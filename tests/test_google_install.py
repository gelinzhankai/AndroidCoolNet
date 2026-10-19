import contextlib
import copy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('google_install_test', ROOT/'setup_tool.py')
s = importlib.util.module_from_spec(spec)
spec.loader.exec_module(s)
PACKAGES = s.GOOGLE_PACKAGES
CATALOG = json.loads((ROOT/'config/gms-packages.json').read_text())['packages']


class FakeAdb:
    def __init__(self, installed=(), known=(), disabled=()):
        self.installed, self.known, self.disabled = set(installed), set(known)|set(installed), set(disabled)
        self.mutations = []
        self.failure = None
        self.drop_success = False
        self.race = False

    def packages(self, *flags):
        if self.race:
            self.installed.update(PACKAGES)
            self.known.update(PACKAGES)
        return set(self.disabled if '-d' in flags else self.known if '-u' in flags else self.installed)

    def shell(self, *args, **kwargs):
        if args == ('pm', 'list', 'libraries'):
            return ''
        assert args[:5] == ('cmd','package','install-existing','--user','0')
        self.mutations.append(args)
        self.installed.add(args[-1])
        return 'Package installed for user: 0'

    def run(self, *args, **kwargs):
        self.mutations.append(args)
        assert args[:5] == ('install','--no-streaming','-R','--user','0')
        assert '-r' not in args and '-d' not in args
        if self.failure:
            return self.failure
        if not self.drop_success:
            package = Path(args[-1]).read_text()
            self.installed.add(package)
            self.known.add(package)
        return 'Success'


class GoogleInstallTests(unittest.TestCase):
    def device(self, adb, api=35, abis=None):
        return dict(api=api, abis=abis or ['arm64-v8a'], preview_sdk=0, gms={
            p:'disabled' if p in adb.disabled else 'installed' if p in adb.installed else
            'not_installed_for_user' if p in adb.known else 'missing' for p in PACKAGES})

    def provision(self, adb, device=None, alter=None):
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()), mock.patch('builtins.input', return_value=''):
            root = Path(tmp)
            (root/'config').mkdir()
            (root/'cache/gms').mkdir(parents=True)
            entries = copy.deepcopy(CATALOG)
            for e in entries:
                data = e['package'].encode()
                (root/'cache/gms'/e['file']).write_bytes(data)
                e['sha256'] = hashlib.sha256(data).hexdigest()
                e['bytes'] = len(data)
            if alter:
                alter(root, entries)
            (root/'config/gms-packages.json').write_text(json.dumps({'packages':entries}))
            return s.provision_google(adb, device or self.device(adb), root)

    def test_version_and_abi_matrix(self):
        for api in (35,36,37):
            for abi, file in [('arm64-v8a','gms-arm64.apk'),('armeabi-v7a','gms-arm64.apk')]:
                with self.subTest(api=api,abi=abi):
                    d = self.device(FakeAdb(), api, [abi])
                    self.assertEqual(s.select_google_apk(CATALOG, PACKAGES[0], d)['file'], f'gsf-{api}.apk')
                    self.assertEqual(s.select_google_apk(CATALOG, PACKAGES[1], d)['file'], file)

    def test_unsupported_or_preview_does_not_guess(self):
        for api, abi, preview in [(34,'arm64-v8a',0),(38,'arm64-v8a',0),(35,'riscv64',0),(37,'arm64-v8a',1),
                                  (35,'x86_64',0),(36,'x86',0)]:
            d=self.device(FakeAdb(),api,[abi]); d['preview_sdk']=preview
            with self.assertRaises(s.SetupError):
                s.select_google_apk(CATALOG, PACKAGES[1], d)

    def test_existing_all_skipped_even_without_catalog(self):
        adb=FakeAdb(PACKAGES)
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()):
            result=s.provision_google(adb,self.device(adb,34),Path(tmp))
        self.assertTrue(result['complete'])
        self.assertEqual(adb.mutations,[])

    def test_disabled_preserved_and_not_reported_ready(self):
        adb=FakeAdb(PACKAGES,disabled=[PACKAGES[1]])
        result=self.provision(adb)
        self.assertFalse(result['complete'])
        self.assertEqual(result['components'][PACKAGES[1]]['status'],'skipped_disabled')
        self.assertEqual(adb.mutations,[])

    def test_restore_existing_system_code_without_apk(self):
        adb=FakeAdb(PACKAGES[1:],known=PACKAGES)
        result=self.provision(adb,self.device(adb,34))
        self.assertTrue(result['complete'])
        self.assertEqual(len(adb.mutations),1)
        self.assertEqual(result['components'][PACKAGES[0]]['status'],'restored_existing')

    def test_only_missing_component_installed(self):
        adb=FakeAdb([PACKAGES[0],PACKAGES[2]])
        result=self.provision(adb)
        self.assertTrue(result['complete'])
        self.assertEqual(len(adb.mutations),1)
        self.assertEqual(result['components'][PACKAGES[1]]['status'],'installed')

    def test_missing_all_installs_in_dependency_order(self):
        adb=FakeAdb()
        result=self.provision(adb)
        self.assertTrue(result['complete'])
        self.assertEqual([Path(a[-1]).name for a in adb.mutations],['gsf-35.apk','gms-arm64.apk','play-store.apk'])

    def test_corrupt_last_apk_blocks_all_before_mutation(self):
        adb=FakeAdb()
        result=self.provision(adb,alter=lambda root,_:(root/'cache/gms/play-store.apk').write_bytes(b'corrupt'))
        self.assertFalse(result['complete'])
        self.assertEqual(adb.mutations,[])

    def test_missing_system_library_blocks_install(self):
        adb=FakeAdb()
        def alter(_, entries): entries[0]['required_libraries']=['vendor.missing']
        result=self.provision(adb,alter=alter)
        self.assertFalse(result['complete'])
        self.assertEqual(adb.mutations,[])

    def test_installed_after_detection_is_skipped(self):
        adb=FakeAdb(); device=self.device(adb); adb.race=True
        self.assertTrue(self.provision(adb,device)['complete'])
        self.assertEqual(adb.mutations,[])

    def test_known_after_detection_is_restored(self):
        adb=FakeAdb(); device=self.device(adb); adb.known.update(PACKAGES)
        self.assertTrue(self.provision(adb,device)['complete'])
        self.assertTrue(all(a[0]=='cmd' for a in adb.mutations))

    def test_install_failure_blocks_dependents(self):
        adb=FakeAdb(); adb.failure='Failure [INSTALL_FAILED_SHARED_USER_INCOMPATIBLE: details]'
        result=self.provision(adb)
        self.assertFalse(result['complete'])
        self.assertEqual(len(adb.mutations),1)
        self.assertEqual(result['components'][PACKAGES[1]]['status'],'blocked_by_previous_failure')

    def test_success_without_package_fails_postcheck(self):
        adb=FakeAdb(); adb.drop_success=True
        self.assertFalse(self.provision(adb)['complete'])
        self.assertEqual(len(adb.mutations),1)

    def test_path_cannot_leave_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(s.SetupError):
                s.verified_google_apk({'file':'../outside.apk'},Path(tmp))


if __name__=='__main__':
    unittest.main()
