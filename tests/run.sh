#!/usr/bin/env bash
set -euo pipefail
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
platform=${1:-linux/arm64}
case "$platform" in linux/arm64|linux/amd64) ;; *) echo 'Expected linux/arm64 or linux/amd64' >&2; exit 2 ;; esac
tag="cual-verification:${platform#linux/}"
docker build --platform "$platform" -t "$tag" -f "$repo/tests/Dockerfile" "$repo"
mounts=(-v "$repo:/src:ro")
install_options=()
if [[ $# -ge 2 ]]; then
  [[ "$2" = /* && -f "$2" ]] || { echo 'Package must be an existing absolute file path' >&2; exit 2; }
  mounts+=(-v "$2:/package.deb:ro")
  install_options+=(--package /package.deb)
fi
docker run --rm --platform "$platform" "${mounts[@]}" -e PYTHONDONTWRITEBYTECODE=1 "$tag" bash -euc '
  /src/scripts/install.sh --user root --runtime-only --skip-system --yes "$@"
  python3 -m unittest discover -s /src/tests -p "test_*.py" -v
  python3 /src/tests/installer_cli.py
  python3 /src/tests/registration.py
  dbus-run-session -- bash /src/tests/desktop.sh
' -- "${install_options[@]}"
