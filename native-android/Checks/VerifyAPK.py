"""Inspect the actual pilot APK on the remote Android build runner."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import zipfile

output = Path(sys.argv[1])
apks = sorted(output.rglob('*.apk'))
if len(apks) != 1:
    raise SystemExit(f'Expected one ARM64 APK, found {len(apks)}')
apk = apks[0]
sdk = Path(os.environ.get('ANDROID_HOME') or os.environ['ANDROID_SDK_ROOT'])
tools = sorted((sdk / 'build-tools').glob('*'), key=lambda p: tuple(int(n) for n in re.findall(r'\d+', p.name)))
build_tools = next((p for p in reversed(tools) if (p / 'apksigner').is_file() and (p / 'aapt').is_file()), None)
if build_tools is None:
    raise SystemExit('Android build tools with apksigner and aapt are required')

def checked(*args):
    return subprocess.run(args, check=True, capture_output=True, text=True).stdout

signature = checked(str(build_tools / 'apksigner'), 'verify', '--verbose', '--print-certs', str(apk))
badging = checked(str(build_tools / 'aapt'), 'dump', 'badging', str(apk))
package = re.search(r"package: name='([^']+)' versionCode='([^']+)' versionName='([^']+)'", badging)
if not package or package[1] != 'ai.fittracker.app':
    raise SystemExit('APK has an unexpected application ID')
if "launchable-activity:" not in badging:
    raise SystemExit('APK has no launcher activity')
with zipfile.ZipFile(apk) as archive:
    libraries = [p for p in archive.namelist() if p.startswith('lib/') and p.endswith('.so')]
if not libraries or any(not p.startswith('lib/arm64-v8a/') for p in libraries):
    architectures = sorted({p.split('/')[1] for p in libraries})
    raise SystemExit(f'Expected native libraries for ARM64 only; found {architectures}')
certificate = re.search(r'certificate SHA-256 digest:\s*([0-9a-fA-F]{64})', signature)
if certificate is None:
    raise SystemExit('APK signing certificate fingerprint was not returned by apksigner')
expected_certificate = os.environ.get('EXPECTED_SIGNING_CERTIFICATE_SHA256')
if expected_certificate and certificate[1].lower() != expected_certificate.lower():
    raise SystemExit('APK signing certificate does not match the registered Google Android client')
digest = hashlib.sha256()
with apk.open('rb') as stream:
    for block in iter(lambda: stream.read(1024 * 1024), b''):
        digest.update(block)
metadata = {
    'source_commit': os.environ.get('GITHUB_SHA'),
    'package': package[1],
    'version_code': package[2],
    'version_name': package[3],
    'architecture': 'arm64-v8a',
    'apk': apk.name,
    'bytes': apk.stat().st_size,
    'sha256': digest.hexdigest(),
    'certificate_sha256': certificate[1] if certificate else None,
    'distribution': 'pilot-debug-only',
}
(output / 'apk-verification.json').write_text(json.dumps(metadata, indent=2) + '\n')
(output / 'apk-badging.txt').write_text(badging)
(output / 'apk-signature.txt').write_text(signature)
print(json.dumps(metadata, indent=2))
