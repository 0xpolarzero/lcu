#!/usr/bin/env bash
set -euo pipefail
source_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
case "$(uname -s)" in
  Darwin) exec python3 -B "$source_dir/scripts/install_macos.py" "$@" ;;
  Linux) exec python3 -B "$source_dir/scripts/install.py" "$@" ;;
  *) echo "LCU installation currently supports Linux and macOS." >&2; exit 1 ;;
esac
