"""Repackage official IBKR wheel metadata for the patched protobuf runtime.

API source is unchanged. Only Requires-Dist and the wheel RECORD are updated.
The upstream ZIP is SHA256-pinned here and the output wheel in vendor/SHA256.json.
"""
import base64
import csv
import hashlib
import io
from pathlib import Path
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE_SHA256 = "673129e5cba58c4d77bc40647265f84ea42f605eccf88fa4c1221d62d12454f3"
archive = ROOT / ".build/twsapi_macunix.1050.02.zip"
if hashlib.sha256(archive.read_bytes()).hexdigest() != ARCHIVE_SHA256:
    raise SystemExit("Official IBKR archive integrity mismatch")
source = ROOT / ".build/ibkr-api1050"
with zipfile.ZipFile(archive) as zipped:
    for item in zipped.infolist():
        if item.filename.startswith("IBJts/source/pythonclient/"):
            destination = (source / item.filename).resolve()
            if not destination.is_relative_to(source.resolve()):
                raise SystemExit("Unsafe archive path")
            zipped.extract(item, source)
wheel_dir = ROOT / ".build/ibkr-wheel"
subprocess.run([sys.executable, "-m", "pip", "wheel", "--no-deps", "--no-build-isolation", "--wheel-dir", str(wheel_dir),
                str(source / "IBJts/source/pythonclient")], check=True)
name = "ibapi-10.50.2-py3-none-any.whl"
with zipfile.ZipFile(wheel_dir / name) as wheel:
    files = {item.filename: wheel.read(item) for item in wheel.infolist() if not item.is_dir()}
metadata = "ibapi-10.50.2.dist-info/METADATA"
original = files[metadata]
if original.count(b"Requires-Dist: protobuf==5.29.5") != 1:
    raise SystemExit("Unexpected upstream dependency metadata")
files[metadata] = original.replace(b"Requires-Dist: protobuf==5.29.5", b"Requires-Dist: protobuf==5.29.6")
record = "ibapi-10.50.2.dist-info/RECORD"
table = io.StringIO(newline="")
writer = csv.writer(table, lineterminator="\n")
for path, content in sorted(files.items()):
    if path != record:
        digest = base64.urlsafe_b64encode(hashlib.sha256(content).digest()).rstrip(b"=").decode()
        writer.writerow([path, "sha256=" + digest, len(content)])
writer.writerow([record, "", ""])
files[record] = table.getvalue().encode()
output = ROOT / "vendor" / name
with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as wheel:
    for path, content in sorted(files.items()):
        info = zipfile.ZipInfo(path, date_time=(2026, 9, 9, 0, 0, 0))
        info.compress_type = zipfile.ZIP_DEFLATED
        wheel.writestr(info, content)
print("API source unchanged; patched protobuf dependency; wheel SHA256:", hashlib.sha256(output.read_bytes()).hexdigest())
