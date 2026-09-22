#!/usr/bin/env bash
set -euo pipefail
test_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
export DISPLAY=:99 GTK_MODULES=gail:atk-bridge NO_AT_BRIDGE=0
export XDG_RUNTIME_DIR=$(mktemp -d)
export CUAL_TEST_OUTPUT=$(mktemp -d)
processes=()
cleanup() {
  for pid in "${processes[@]}"; do kill "$pid" 2>/dev/null || true; done
  for pid in "${processes[@]}"; do wait "$pid" 2>/dev/null || true; done
  rm -rf "$XDG_RUNTIME_DIR" "$CUAL_TEST_OUTPUT"
}
trap cleanup EXIT
Xvfb :99 -screen 0 1024x768x24 -nolisten tcp >"$CUAL_TEST_OUTPUT/xvfb.log" 2>&1 & processes+=("$!")
for attempt in {1..30}; do
  if xdpyinfo >/dev/null 2>&1; then break; fi
  sleep 0.1
done
openbox >"$CUAL_TEST_OUTPUT/openbox.log" 2>&1 & processes+=("$!")
python3 "$test_dir/fixture.py" >"$CUAL_TEST_OUTPUT/fixture.log" 2>&1 & processes+=("$!")
python3 "$test_dir/x11_fixture.py" >"$CUAL_TEST_OUTPUT/x11-fixture.log" 2>&1 & processes+=("$!")
command=("$@")
if [[ ${#command[@]} -eq 0 ]]; then command=(/opt/cual/current/bin/cual); fi
"${command[@]}" doctor
python3 "$test_dir/integration.py" "${command[@]}"
