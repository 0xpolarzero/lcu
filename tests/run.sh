#!/usr/bin/env bash
set -euo pipefail
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
platform=${1:-linux/arm64}
case "$platform" in linux/arm64|linux/amd64) ;; *) echo 'Expected linux/arm64 or linux/amd64' >&2; exit 2 ;; esac
tag="lcu-verification:${platform#linux/}"
docker build --platform "$platform" -t "$tag" -f "$repo/tests/Dockerfile" "$repo"
mkdir -p "$repo/.verification"
output=$(mktemp -d "$repo/.verification/${platform#linux/}.XXXXXX")
package=${2:-$output/upstream.deb}
if [[ $# -ge 2 ]]; then
  [[ "$package" = /* && -f "$package" ]] || { echo 'Package must be an existing absolute file path' >&2; exit 2; }
else
# Keep the pinned source package for offline install validation.
  docker run --rm --platform "$platform" -v "$repo:/src:ro" -v "$output:/out" "$tag" python3 -c '
import json,sys
from pathlib import Path
sys.path.insert(0,"/src/scripts")
from bundle import architecture
from installed_app import _download
lock=json.loads(Path("/src/runtime.lock.json").read_text()); entry=lock["architectures"][architecture()]
_download(lock,entry,Path("/out/upstream.deb"))
'
fi
mounts=(-v "$repo:/src:ro" -v "$package:/package.deb:ro")
docker run --rm --platform "$platform" -v "$repo:/src:ro" -v "$output:/out" \
  -e PYTHONDONTWRITEBYTECODE=1 "$tag" \
  python3 /src/scripts/build_bundle.py --output /out
archive=$(find "$output" -maxdepth 1 -name '*.tar.gz' -print)
[[ -n "$archive" ]] || exit 1
docker run --rm --network none --platform "$platform" "${mounts[@]}" -v "$output:/bundles:ro" \
  -e PYTHONDONTWRITEBYTECODE=1 "$tag" \
  bash /src/tests/offline.sh "/bundles/$(basename -- "$archive")" /package.deb
printf 'Archive and evidence: %s\n' "$output"
