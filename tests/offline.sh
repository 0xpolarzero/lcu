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
# A bad package must not change the already selected release.
selected=$(readlink -f /opt/lcu/current)
printf 'corrupt package' >/tmp/corrupt-chatgpt.deb
if "$bundle/scripts/install.sh" --prefix /opt/lcu --user lcutester \
  --runtime-only --skip-system --app-package /tmp/corrupt-chatgpt.deb --offline --yes \
  >/tmp/lcu-install-failure.log 2>&1; then
  echo 'Installer accepted a package with the wrong checksum' >&2
  exit 1
fi
test "$(readlink -f /opt/lcu/current)" = "$selected"

# A system-library acquisition failure in a separate installer process must
# leave the selected release usable. Shadow apt-get only inside this command;
# the disposable test image and host package manager remain unchanged.
mkdir /tmp/lcu-failing-apt
cat >/tmp/lcu-failing-apt/apt-get <<'SH'
#!/bin/sh
printf '%s\n' "$*" >/tmp/lcu-apt-invoked
exit 100
SH
chmod +x /tmp/lcu-failing-apt/apt-get
if PATH="/tmp/lcu-failing-apt:$PATH" "$bundle/scripts/install.sh" --prefix /opt/lcu --user lcutester \
  --runtime-only --app-package "$package" --yes \
  >/tmp/lcu-apt-failure.log 2>&1; then
  echo 'Installer selected a release after system-library acquisition failed' >&2
  exit 1
fi
test "$(cat /tmp/lcu-apt-invoked)" = update
test "$(readlink -f /opt/lcu/current)" = "$selected"
test -f "$selected/bin/lcu"

# Exercise separate Python/installer processes racing on the same prefix. Both
# reuse the managed application generation and verified package cache above.
"$bundle/scripts/install.sh" --prefix /opt/lcu --user lcutester \
  --runtime-only --skip-system --app-package "$package" --offline --yes \
  >/tmp/lcu-install-a.log 2>&1 &
first=$!
"$bundle/scripts/install.sh" --prefix /opt/lcu --user lcutester \
  --runtime-only --skip-system --app-package "$package" --offline --yes \
  >/tmp/lcu-install-b.log 2>&1 &
second=$!
status=0
wait "$first" || status=$?
wait "$second" || status=$?
if [[ $status -ne 0 ]]; then
  cat /tmp/lcu-install-a.log /tmp/lcu-install-b.log >&2
  exit "$status"
fi
python3 - /opt/lcu <<'PY'
import hashlib, json, os, platform, stat
from pathlib import Path
import sys
sys.path.insert(0, '/src/scripts')
from bundle import architecture

prefix = Path('/opt/lcu')
current = prefix / 'current'
assert current.is_symlink(), 'current is not a symlink'
release = current.resolve(strict=True)
assert release.parent == (prefix / 'releases').resolve()
manifest = json.loads((release / 'bundle.json').read_text())
assert manifest['architecture'] == architecture()
descriptor = json.loads((release / 'installation.json').read_text())
application = (release / descriptor['app']).resolve(strict=True)
assert application.is_dir()
actual = {}
for path in sorted(release.rglob('*')):
    relative = path.relative_to(release).as_posix()
    if relative in {'bundle.json', 'installation.json', 'app'}:
        continue
    mode = path.lstat().st_mode
    if stat.S_ISLNK(mode):
        target = os.readlink(path)
        resolved = path.resolve()
        assert not Path(target).is_absolute() and (resolved.is_relative_to(release) or resolved.is_relative_to(application)), f'unsafe release symlink: {relative} -> {target}'
        actual[relative] = {'type': 'symlink', 'target': target}
    elif stat.S_ISREG(mode):
        with path.open('rb') as stream:
            digest = hashlib.file_digest(stream, 'sha256').hexdigest()
        actual[relative] = {'type': 'file', 'sha256': digest, 'mode': mode & 0o777}
    elif not stat.S_ISDIR(mode):
        raise AssertionError(f'unsupported release entry: {relative}')
assert actual == manifest['files'], 'selected release does not match its bundle manifest'
assert (application / 'resources/cua_node/manifest.json').is_file()
PY
test ! -e /opt/lcu/.next
test -z "$(find /opt/lcu/releases -maxdepth 1 -name '.build-*' -print -quit)"
test -z "$(find /opt/lcu/apps -maxdepth 1 -name '.app-stage-*' -print -quit)"
test -z "$(find /opt/lcu/cache -maxdepth 1 \( -name '.*.stage' -o -name '.*.download' \) -print -quit)"
python3 -m unittest discover -s /src/tests -p 'test_*.py' -q
python3 /src/tests/registration.py
runuser -u lcutester -- dbus-run-session -- bash /src/tests/desktop.sh
