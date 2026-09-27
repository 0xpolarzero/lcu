#!/bin/sh
# Copies the showreel and its poster from docs/assets into site/media.
# Run before previewing or deploying (the Vercel deploy uploads site/ as-is).
set -eu
root=$(cd "$(dirname "$0")/.." && pwd)
mkdir -p "$root/site/media"
cp "$root/docs/assets/lcu-showreel.mp4" "$root/docs/assets/lcu-showreel-poster.jpg" "$root/site/media/"
