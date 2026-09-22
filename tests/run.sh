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
  # Keep the independent source package for the mandatory differential gate.
  docker run --rm --platform "$platform" -v "$repo:/src:ro" -v "$output:/out" "$tag" python3 -c '
import json,sys
from pathlib import Path
sys.path.insert(0,"/src/scripts")
from bundle import architecture
from project_runtime import download
lock=json.loads(Path("/src/runtime.lock.json").read_text()); entry=lock["architectures"][architecture()]
download(lock["source"].format(deb_arch=entry["deb_arch"]),Path("/out/upstream.deb"),entry["sha256"])
'
fi
mounts=(-v "$repo:/src:ro" -v "$package:/package.deb:ro")
docker run --rm --platform "$platform" "${mounts[@]}" -v "$output:/out" -e PYTHONDONTWRITEBYTECODE=1 "$tag" \
  python3 /src/scripts/build_bundle.py --output /out --package /package.deb
archive=$(find "$output" -maxdepth 1 -name '*.tar.gz' -print)
[[ -n "$archive" ]] || exit 1
docker run --rm --network none --platform "$platform" -v "$repo:/src:ro" -v "$output:/bundles:ro" \
  -e PYTHONDONTWRITEBYTECODE=1 "$tag" bash /src/tests/offline.sh "/bundles/$(basename -- "$archive")"
docker run --rm --network none --platform "$platform" "${mounts[@]}" -v "$output:/out" \
  -e DIFFERENTIAL_AUDIO=1 -e DIFFERENTIAL_XFCE=1 -e PYTHONDONTWRITEBYTECODE=1 "$tag" \
  bash /src/tests/differential.sh /package.deb "/out/$(basename -- "$archive")" /out/differential
printf 'Archive and evidence: %s\n' "$output"
