#!/usr/bin/env bash
set -euo pipefail
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
platform=${1:-linux/arm64}
case "$platform" in linux/arm64|linux/amd64) ;; *) echo 'Expected linux/arm64 or linux/amd64' >&2; exit 2 ;; esac
tag="lcu-verification:${platform#linux/}"
docker build --platform "$platform" -t "$tag" -f "$repo/tests/Dockerfile" "$repo"
mounts=(-v "$repo:/src:ro")
build_options=()
if [[ $# -ge 2 ]]; then
  [[ "$2" = /* && -f "$2" ]] || { echo 'Package must be an existing absolute file path' >&2; exit 2; }
  mounts+=(-v "$2:/package.deb:ro")
  build_options+=(--package /package.deb)
fi
# Building can download pinned inputs. The separate installation/test container cannot.
output=$(mktemp -d)
trap 'rm -rf "$output"' EXIT
docker run --rm --platform "$platform" "${mounts[@]}" -v "$output:/out" -e PYTHONDONTWRITEBYTECODE=1 "$tag" \
  python3 /src/scripts/build_bundle.py --output /out "${build_options[@]}"
docker run --rm --network none --platform "$platform" -v "$repo:/src:ro" -v "$output:/bundles:ro" \
  -e PYTHONDONTWRITEBYTECODE=1 "$tag" bash -euc 'exec bash /src/tests/offline.sh /bundles/*.tar.gz'
