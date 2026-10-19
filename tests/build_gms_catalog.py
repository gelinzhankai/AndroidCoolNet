"""Maintainer-only: verify real APKs with Android SDK, then pin their metadata."""
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
BT = Path(r'C:\Android\Sdk\build-tools\35.0.0')
JAVA = Path(r'C:\Program Files\Microsoft\jdk-21.0.9.10-hotspot\bin\java.exe')
BASE = 'https://www.apkmirror.com/apk/google-inc/'
SOURCES = {
    'gsf-35.apk': ('google-services-framework/google-services-framework-15-release/google-services-framework-15-12-android-apk-download/', 35, 35),
    'gsf-36.apk': ('google-services-framework/google-services-framework-16-release/google-services-framework-16-25-android-apk-download/', 36, 36),
    'gsf-37.apk': ('google-services-framework/google-services-framework-17-release/google-services-framework-17-5-android-apk-download/', 37, 37),
    'gms-arm64.apk': ('google-play-services/google-play-services-26-40-32-release/google-play-services-26-40-32-260400-995630914-android-apk-download/', 35, 37),
    'play-store.apk': ('google-play-store/google-play-store-53-4-35-release/google-play-store-53-4-35-34-0-pr-991305241-2-android-apk-download/', 35, 37),
}
def run(*args):
    args = [a.relative_to(ROOT) if isinstance(a, Path) and a.is_relative_to(ROOT) else a for a in args]
    return subprocess.check_output([str(a) for a in args], cwd=ROOT, encoding='utf-8', errors='replace')

entries = []
for filename, (source, low, high) in SOURCES.items():
    path = ROOT / 'cache/gms' / filename
    chain = run(JAVA, '-cp', BT/'lib/apksigner.jar', ROOT/'tests/VerifyGoogle.java', path).splitlines()
    badging = run(BT/'aapt.exe', 'dump', 'badging', path)
    xml = run(BT/'aapt.exe', 'dump', 'xmltree', path, 'AndroidManifest.xml')
    assert 'isSplitRequired' not in xml and 'com.android.vending.splits.required' not in xml
    package, code, version = re.search(r"package: name='([^']+)' versionCode='(\d+)' versionName='([^']+)'", badging).groups()
    abi_lines = re.findall(r'^(?:alt-)?native-code: (.*)$', badging, re.M)
    abis = [a for line in abi_lines for a in re.findall(r"'([^']+)'", line)] or ['noarch']
    min_sdk = int(re.search(r"sdkVersion:'(\d+)'", badging)[1])
    target = int(re.search(r"targetSdkVersion:'(\d+)'", badging)[1])
    with path.open('rb') as stream:
        sha = hashlib.file_digest(stream, 'sha256').hexdigest()
    entries.append(dict(package=package, file=filename, version_code=int(code), version_name=version,
                        min_sdk=min_sdk, target_sdk=target, supported_api_min=low, supported_api_max=high,
                        abis=abis, sha256=sha, bytes=path.stat().st_size, certificate_lineage_sha256=chain,
                        required_libraries=re.findall(r"^uses-library:'([^']+)'", badging, re.M), source=BASE+source,
                        validation='APK signature and manifest verified; OEM runtime/login not verified'))
    print(filename, package, min_sdk, target, abis, sha)
(ROOT/'config/gms-packages.json').write_text(json.dumps({'schema':1, 'packages':entries}, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
