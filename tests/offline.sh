#!/usr/bin/env bash
# Run inside the disposable test image with --network none.
set -euo pipefail
archive=${1:?Provide the release archive}
cd "$(dirname -- "$archive")"
name=$(basename -- "$archive")
sha256sum -c "$name.sha256"
python3 -c 'from pathlib import Path; assert {p.name for p in Path("/sys/class/net").iterdir()} == {"lo"}, "Test requires --network none"'
tar -xzf "$name" -C /opt
bundle="/opt/${name%.tar.gz}"
"$bundle/scripts/install.sh" --user root --runtime-only --skip-system --yes
python3 -m unittest discover -s /src/tests -p 'test_*.py' -v
python3 /src/tests/installer_cli.py "$bundle"
python3 /src/tests/registration.py
dbus-run-session -- bash /src/tests/desktop.sh
