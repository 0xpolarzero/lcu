#!/usr/bin/env bash
set -euo pipefail
release=${1:?Expected an extracted release root}
export LCU_TEST_RELEASE="$release"
"$release/runtime/bin/node" "$(dirname "$0")/iab_account_context.cjs" "${2:-$release/host/application}"
