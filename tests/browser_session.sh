#!/usr/bin/env bash
set -euo pipefail
release=/fixture/release
"$release/bin/lcu" browser install
Xvfb :99 -screen 0 1280x800x24 >/tmp/lcu-browser-xvfb.log 2>&1 &
xvfb_pid=$!
export DISPLAY=:99
"$release/runtime/bin/node" /src/tests/browser_launch.mjs >/tmp/lcu-browser.log 2>&1 &
browser_pid=$!
cleanup() {
  kill "$browser_pid" "$xvfb_pid" 2>/dev/null || true
  wait "$browser_pid" "$xvfb_pid" 2>/dev/null || true
}
trap cleanup EXIT
for attempt in $(seq 1 60); do
  [[ -f /tmp/lcu-browser-ready ]] && break
  sleep 0.2
done
[[ -f /tmp/lcu-browser-ready ]] || { cat /tmp/lcu-browser.log; exit 1; }
python3 -B /src/tests/browser_runtime.py "$release" /original/cua_node
