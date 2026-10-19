"""Offline API35 acceptance; only a disposable probe is installed/disabled/removed."""
import contextlib
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shutil
import tempfile
import zipfile
from unittest import mock
import gms_assets

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('google_emulator_test',ROOT/'setup_tool.py')
s=importlib.util.module_from_spec(spec); spec.loader.exec_module(s)
adb=s.Adb(r'H:\Android-Emulator\sdk\platform-tools\adb.exe','emulator-5580')
assert 'Codex_API35_Play' in adb.run('emu','avd','name')
assert adb.shell('settings','get','global','airplane_mode_on')=='1'
assert adb.shell('settings','get','global','wifi_on')=='0'
assert adb.shell('settings','get','global','http_proxy') in ('null',':0')
assert 'Active default network: none' in adb.shell('dumpsys','connectivity')

def versions():
    return {p: re.findall(r'(?:versionCode=\d+|versionName=[^\n]+|lastUpdateTime=[^\n]+)',
                          adb.shell('dumpsys','package',p)) for p in s.GOOGLE_PACKAGES}

before=versions()
device,_=s.inspect_device(adb)
result=s.provision_google(adb,device)
assert result['complete'] and all(x['status']=='already_installed' for x in result['components'].values())
assert versions()==before

probe='test.androidsetup.excluded'
assert probe not in adb.packages('-u'), 'Refuse to modify a pre-existing probe'
evidence={'google_existing_untouched':True,'google_versions':before,'offline':True,'device':device}
try:
    with tempfile.TemporaryDirectory() as tmp, mock.patch.object(s,'GOOGLE_PACKAGES',(probe,)):
        root=Path(tmp); (root/'config').mkdir()
        source=ROOT/'tests/artifacts/probe-build/excluded.apk'
        apk=root/'cache/gms/probe.apk'
        entry=dict(package=probe,file=apk.name,version_name='1',supported_api_min=35,supported_api_max=35,
                   min_sdk=24,abis=['noarch'],required_libraries=[],bytes=source.stat().st_size,
                   sha256=hashlib.sha256(source.read_bytes()).hexdigest())
        (root/'config/gms-packages.json').write_text(json.dumps({'packages':[entry]}))
        offline=root/'probe-offline.zip'
        with zipfile.ZipFile(offline, 'w') as archive:
            archive.write(source, 'nested/renamed.apk')
        device,_=s.inspect_device(adb)
        with mock.patch('builtins.input', side_effect=['2', '', str(offline)]), mock.patch.object(gms_assets.webbrowser, 'open'):
            first=s.provision_google(adb,device,root)
        assert first['components'][probe]['status']=='installed' and first['complete']
        evidence['probe_fresh_install']=True
        evidence['manual_zip_import_before_install']=True
        device,_=s.inspect_device(adb)
        second=s.provision_google(adb,device,root)
        assert second['components'][probe]['status']=='already_installed'
        output=adb.run('install','--no-streaming','-R','--user','0',apk,check=False,include_stderr=True,timeout=180)
        assert 'INSTALL_FAILED_ALREADY_EXISTS' in output, output
        evidence['android_no_replace_guard']=True
        adb.shell('pm','disable-user','--user','0',probe)
        device,_=s.inspect_device(adb)
        disabled=s.provision_google(adb,device,root)
        assert disabled['components'][probe]['status']=='skipped_disabled' and not disabled['complete']
        assert probe in adb.packages('-d')
        evidence['disabled_preserved']=True
finally:
    if probe in adb.packages('-u'):
        adb.run('uninstall',probe)
assert probe not in adb.packages('-u')
assert versions()==before
assert 'Active default network: none' in adb.shell('dumpsys','connectivity')
evidence['probe_removed']=True
(ROOT/'tests/artifacts/google-acceptance.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2),encoding='utf-8')
print('PASS: real Google packages unchanged; disposable probe fresh-install/skip/no-replace/disabled paths; offline.')
