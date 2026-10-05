"""Sign nested Mach-O code inside-out; never bundle user data or signing keys."""
from pathlib import Path
import subprocess
import sys

root = Path(sys.argv[1]).resolve()
identity = sys.argv[2]
if root.name != "Beta Dashboard Finanziaria.app" or not root.is_dir():
    raise SystemExit("Unexpected application target")
options = ["--force", "--sign", identity]
if identity != "-":
    options.extend(["--timestamp", "--options", "runtime"])
for path in sorted(root.rglob("*"), key=lambda p: len(p.parts), reverse=True):
    if path.is_file() and not path.is_symlink():
        kind = subprocess.check_output(["/usr/bin/file", "-b", str(path)], text=True)
        if "Mach-O" in kind:
            subprocess.run(["/usr/bin/codesign", *options, str(path)], check=True)
    elif path.suffix == ".framework":
        subprocess.run(["/usr/bin/codesign", *options, str(path)], check=True)
subprocess.run(["/usr/bin/codesign", *options, str(root)], check=True)
