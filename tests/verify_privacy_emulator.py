"""Offline emulator acceptance with a disposable probe, never the real target application."""
from pathlib import Path
import sys
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import setup_tool as s

adb = s.Adb(sys.argv[1], 'emulator-5580')
apk = Path(sys.argv[2]).resolve()
probe = 'test.androidsetup.excluded'
assert 'Codex_API35_Play' in adb.run('emu', 'avd', 'name')
assert adb.shell('settings', 'get', 'global', 'airplane_mode_on') == '1'
assert adb.shell('settings', 'get', 'global', 'wifi_on') == '0'
assert adb.shell('settings', 'get', 'global', 'http_proxy') in ('null', ':0')
assert 'Active default network: none' in adb.shell('dumpsys', 'connectivity')
assert adb.shell('am', 'get-current-user') == '0'
assert probe not in adb.packages('-u'), 'Refuse to change a pre-existing probe'
assert s.ANTIFRAUD_PACKAGE not in adb.packages('-u'), 'Refuse testing alongside a real target'
before = adb.packages()
try:
    assert 'Success' in adb.run('install', '--no-streaming', '-R', '--user', '0', apk, timeout=120)
    with mock.patch.object(s, 'ANTIFRAUD_PACKAGE', probe), mock.patch('builtins.input', side_effect=['2', '']):
        kept = s.optional_antifraud_removal(adb, adb.packages())
        assert kept['status'] == 'kept' and probe in adb.packages()
        removed = s.optional_antifraud_removal(adb, adb.packages())
        assert removed['status'] == 'uninstalled' and removed['uninstall_attempted']
        assert probe not in adb.packages()
finally:
    if probe in adb.packages('-u'):
        adb.run('uninstall', probe, check=False)
assert adb.packages() == before
assert 'Active default network: none' in adb.shell('dumpsys', 'connectivity')
print('PASS: offline emulator probe retained for 2, removed for Enter; original packages preserved')
