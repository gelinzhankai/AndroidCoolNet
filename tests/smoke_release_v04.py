"""Verify split release contents and run its own runtime against the offline test emulator."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
VERSION = sys.argv[1] if len(sys.argv) > 1 else 'v0.6.1'
DIST = ROOT / 'dist' / VERSION


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


for line in (DIST/'SHA256SUMS.txt').read_text().splitlines():
    expected, name = line.split('  ', 1)
    assert sha(DIST/name) == expected, name

with tempfile.TemporaryDirectory(prefix='AndroidCoolNet-release-') as temp:
    dest = Path(temp)
    with zipfile.ZipFile(DIST/f'AndroidCoolNet-Windows-{VERSION}.zip') as archive:
        names = archive.namelist()
        assert not any('cache/gms/' in n or 'cache/ai/' in n or 'x86_64-release.apk' in n or '/tests/' in n or '/reports/' in n for n in names)
        assert sum(n.endswith('.apk') for n in names) == (2 if VERSION in ('v0.5.0', 'v0.5.1', 'v0.6.0', 'v0.6.1') else 1)
        archive.extractall(dest)
    app = dest/'AndroidCoolNet'
    if VERSION in ('v0.5.0', 'v0.5.1', 'v0.6.0', 'v0.6.1'):
        helper_meta = json.loads((app/'config/clipboard-helper.json').read_text())
        assert sha(app/'cache/androidcoolnet-clipboard.apk') == helper_meta['sha256']
        assert (app/'config/override.yaml').is_file()
    if VERSION in ('v0.6.0', 'v0.6.1'):
        assert (app/'ai_apps.py').is_file()
        ai_catalog = json.loads((app/'config/ai-apps.json').read_text())['apps']
        assert {e['package'] for e in ai_catalog} == {'com.openai.chatgpt', 'com.anthropic.claude'}
        assert all(len(e['certificate_sha256']) == 64 and len(e['archive_sha256']) == 64 for e in ai_catalog)
        if VERSION == 'v0.6.1':
            for entry in ai_catalog:
                assert sha(DIST/entry['file']) == entry['archive_sha256']
                assert (DIST/entry['file']).stat().st_size == entry['bytes']
                assert entry['download_url'].endswith('/download/v0.6.1/' + entry['file'])
    if VERSION == 'v0.4.1':
        assert (app/'PRIVACY_NOTICE.md').is_file()
    manifest = json.loads((app/'SHA256.json').read_text())
    for relative, expected in manifest.items():
        assert sha(app/relative) == expected, relative
    catalog = json.loads((app/'config/gms-packages.json').read_text())['packages']
    assert len(catalog) == 5
    for entry in catalog:
        assert sha(DIST/entry['download_asset']) == entry['download_sha256']
        assert (DIST/entry['download_asset']).stat().st_size == entry['download_bytes']
    with zipfile.ZipFile(DIST/f'AndroidCoolNet-Google-Offline-{VERSION}.zip') as archive:
        apks = {Path(n).name: n for n in archive.namelist() if n.endswith('.apk')}
        assert set(apks) == {e['file'] for e in catalog}
        for entry in catalog:
            with archive.open(apks[entry['file']]) as stream:
                assert hashlib.file_digest(stream, 'sha256').hexdigest() == entry['sha256']

    python = str(app/'runtime/python.exe')
    # With no global Python or SDK dependency, validate the runtime and APK import.
    snippet = '''import json, sys, tempfile
from pathlib import Path
from gms_assets import import_paths, cached
root=Path(sys.argv[1])
catalog=json.loads((root/'config/gms-packages.json').read_text())['packages']
for api in (35,36,37):
    entry=next(e for e in catalog if e['file']==f'gsf-{api}.apk')
    with tempfile.TemporaryDirectory() as cache:
        assert import_paths(sys.argv[2],[entry],Path(cache))=={entry['file']}
        assert cached(Path(cache),entry)
print('PASS: bundled runtime imports each GSF from the offline ZIP')
'''
    subprocess.run([python, '-X', 'utf8', '-c', snippet, str(app), str(DIST/f'AndroidCoolNet-Google-Offline-{VERSION}.zip')], check=True, timeout=120)
    if '--offline-only' in sys.argv:
        subprocess.run([python, '-X', 'utf8', str(app/'setup_tool.py'), '--help'], check=True, timeout=30, stdout=subprocess.DEVNULL)
        print('PASS: release hashes, separate AI archives, base exclusion, portable runtime; no device access.')
        sys.exit(0)
    # Read-only inventory and all-installed branch; explicitly target the isolated emulator.
    adb = str(app/'platform-tools/adb.exe')
    def shell(*args):
        return subprocess.check_output([adb, '-s', 'emulator-5580', *args], encoding='utf-8', timeout=30)
    assert 'Codex_API35_Play' in shell('emu','avd','name')
    assert 'Active default network: none' in shell('shell','dumpsys','connectivity')
    command = [python, '-X', 'utf8', str(app/'setup_tool.py'), '--serial', 'emulator-5580']
    subprocess.run(command + ['--detect-only'], check=True, timeout=90)
    subprocess.run(command + ['--gms-only'], check=True, timeout=90)
    report = json.loads(next((app/'reports').glob('*.json')).read_text(encoding='utf-8'))
    assert report['google_install']['complete']
    if VERSION == 'v0.4.1':
        assert report['privacy_check']['status'] == 'not_installed'
    assert all(x['status']=='already_installed' for x in report['google_install']['components'].values())
    if VERSION in ('v0.5.1', 'v0.6.0', 'v0.6.1'):
        assert report['play_store']['status'] == 'launcher_available'
        assert report['play_store']['system_app']
        assert report['play_store']['launch_status'] == 'not_requested'
    assert not (app/'cache/gms').exists()
    assert 'Active default network: none' in shell('shell','dumpsys','connectivity')

print('PASS: release hashes, base exclusion, offline APK hashes, portable runtime, existing GMS unchanged/no download')
