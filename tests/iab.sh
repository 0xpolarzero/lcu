#!/usr/bin/env bash
# Provider/settings/auth gates against an extracted candidate, offline and private.
set -euo pipefail
release=${1:?Expected installed release root}
output=${2:?Expected an empty evidence directory}
tests=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
mkdir -p "$output"
[[ -z $(ls -A "$output") ]] || { echo 'Evidence directory must be empty' >&2; exit 2; }
export HOME="$output/home" CODEX_HOME="$output/home/.codex"
export XDG_DATA_HOME="$HOME/.local/share" XDG_CONFIG_HOME="$HOME/.config"
export XDG_RUNTIME_DIR="$output/xdg" DISPLAY=:98
export PYTHONDONTWRITEBYTECODE=1 LCU_TEST_RELEASE="$release"
mkdir -p "$CODEX_HOME" "$XDG_RUNTIME_DIR"
chmod 700 "$XDG_RUNTIME_DIR"
processes=()
cleanup() {
  for pid in "${processes[@]}"; do kill "$pid" 2>/dev/null || true; done
  for pid in "${processes[@]}"; do wait "$pid" 2>/dev/null || true; done
}
trap cleanup EXIT
Xvfb :98 -screen 0 1440x900x24 -nolisten tcp >"$output/xvfb.log" 2>&1 & processes+=("$!")
for attempt in {1..50}; do if xdpyinfo >/dev/null 2>&1; then break; fi; sleep .1; done
openbox >"$output/openbox.log" 2>&1 & processes+=("$!")
python3 "$tests/iab_host.py" "$release" >"$output/provider.json" 2>"$output/provider.log"
bash "$tests/iab_auth.sh" "$release" >"$output/auth.json" 2>"$output/auth.log"
"$release/runtime/bin/node" "$tests/iab_account_context.cjs" "${DIFFERENTIAL_UPSTREAM_RUNTIME%/resources/cua_node}" >"$output/account-context.json" 2>"$output/account-context.log"
bash "$tests/iab_http.sh" "$release" >"$output/http.log" 2>&1
bash "$tests/iab_deep_links.sh" "$release" >"$output/deep-links.log" 2>&1
python3 "$tests/iab_protocol.py" "$release" >"$output/protocol.json" 2>"$output/protocol.log"
python3 "$tests/iab_settings.py" "$release/host/application" "$release/host/iab" "$output/settings" --release "$release" >"$output/settings.log" 2>&1
python3 "$tests/iab_permissions.py" "$release" "$output/permissions" >"$output/permissions.log" 2>&1
python3 "$tests/iab_annotation.py" "$release" "$output/annotation" >"$output/annotation.log" 2>&1
python3 "$tests/iab_commands.py" "$release" "$output/commands" >"$output/commands.log" 2>&1
python3 "$tests/browser_runtime.py" --iab-configurations "$release" "${DIFFERENTIAL_UPSTREAM_RUNTIME:?Expected independent original runtime}" "$output/configurations.json" >"$output/configurations.log" 2>&1
python3 "$tests/iab_client_actions.py" "$release" "$DIFFERENTIAL_UPSTREAM_RUNTIME" "$output/client-actions.json" >"$output/client-actions.log" 2>&1
echo 'PASS: installed IAB provider, auth failures/cache, streamed HTTP IPC, deep-link queue/parser, persisted settings, permission UI, native browser commands and effective API restrictions'
