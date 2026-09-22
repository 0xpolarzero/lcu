#!/usr/bin/env bash
set -euo pipefail
release=${1:?Expected an extracted release root}
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
fixture=$(mktemp -d)
source "$repo/tests/iab_cleanup_fixture.sh"
trap 'trap_fixture_cleanup "$fixture"' EXIT
mkdir -p "$fixture/app" "$fixture/profile"
printf '%s\n' '{"name":"lcu-auth-fixture","version":"0.0.0","main":"main.cjs"}' > "$fixture/app/package.json"
python3 - "$repo/tests/iab_auth.cjs" "$fixture/app/main.cjs" <<'PY'
import json,sys
from pathlib import Path
Path(sys.argv[2]).write_text('require('+json.dumps(sys.argv[1])+');\n')
PY
export LCU_APPLICATION_PATH="$release/host/application"
export LCU_TEST_RELEASE="$release"
export LCU_IAB_PROVIDER_PATH="$release/host/iab/provider.cjs"
# Root is used only in the disposable --network none verification container.
"$LCU_APPLICATION_PATH/ChatGPT" --no-sandbox --user-data-dir="$fixture/profile" "$fixture/app"
