#!/usr/bin/env bash
set -euo pipefail
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
platform=${1:?Expected linux/arm64 or linux/amd64}
bundle=${2:?Expected an absolute complete LCU release archive}
upstream=${3:?Expected the original extracted usr/lib/chatgpt/resources directory}
case "$platform" in linux/arm64|linux/amd64) ;; *) exit 2 ;; esac
[[ "$bundle" = /* && -f "$bundle" && "$upstream" = /* && -d "$upstream/cua_node" ]] || exit 2
context=$(mktemp -d)
trap 'rm -rf "$context"' EXIT
cp "$bundle" "$context/bundle.tar.gz"
cp "$repo/tests/browser_extension.py" "$context/browser_extension.py"
cp "$repo/tests/browser.Dockerfile" "$context/Dockerfile"
tag="lcu-browser-verification:${platform#linux/}"
docker build --platform "$platform" --build-arg "BASE_IMAGE=${LCU_BROWSER_TEST_BASE:-lcu-verification:${platform#linux/}}" -t "$tag" "$context"
docker run --rm --network none --platform "$platform" -v "$repo:/src:ro" -v "$upstream:/original:ro" \
  "$tag" dbus-run-session -- bash /src/tests/browser_session.sh
