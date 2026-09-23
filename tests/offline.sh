#!/usr/bin/env bash
# Run inside the disposable Ubuntu test image with --network none.
set -euo pipefail
archive=${1:?Provide the thin LCU archive}
package=${2:?Provide the pinned official ChatGPT package}
cd "$(dirname -- "$archive")"
name=$(basename -- "$archive")
sha256sum -c "$name.sha256"
python3 -c 'from pathlib import Path; assert {p.name for p in Path("/sys/class/net").iterdir()} == {"lo"}, "Test requires --network none"'
python3 - "$package" /src/runtime.lock.json <<'PY'
import hashlib, json, platform, sys
from pathlib import Path
arch = {'aarch64': 'arm64', 'x86_64': 'x64'}[platform.machine()]
lock = json.loads(Path(sys.argv[2]).read_text())
with open(sys.argv[1], 'rb') as stream:
    assert hashlib.file_digest(stream, 'sha256').hexdigest() == lock['architectures'][arch]['sha256']
PY
tar -xzf "$name" -C /opt
bundle="/opt/${name%.tar.gz}"
useradd --create-home lcutester
"$bundle/scripts/install.sh" --prefix /opt/lcu --user lcutester \
  --runtime-only --skip-system --app-package "$package" --offline --yes
python3 -m unittest discover -s /src/tests -p 'test_*.py' -q
python3 /src/tests/registration.py
runuser -u lcutester -- dbus-run-session -- bash /src/tests/desktop.sh
