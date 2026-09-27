#!/bin/sh
# Copies the showreel, its poster and the icon from docs/assets into site/media.
# The Pages workflow runs this before upload; run it locally before previewing.
set -eu
root=$(cd "$(dirname "$0")/.." && pwd)
mkdir -p "$root/site/media"
cp "$root/docs/assets/lcu-showreel.mp4" "$root/docs/assets/lcu-showreel-poster.jpg" "$root/site/media/"
