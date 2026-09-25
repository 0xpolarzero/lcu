#!/usr/bin/env bash
# Build and launch a task-owned AppKit window for original CUA native-action tests.
set -euo pipefail

fixture_root="${1:-$(mktemp -d /private/tmp/lcu-macos-native-fixture.XXXXXX)}"
if [[ -e "$fixture_root/LCUMacFixture.app" ]]; then
  echo "Fixture app already exists: $fixture_root" >&2
  exit 2
fi
mkdir -p "$fixture_root/LCUMacFixture.app/Contents/MacOS"
fixture_root="$(cd "$fixture_root" && pwd -P)"
bundle_id="dev.lcu.NativeFixture.$(uuidgen | tr -d '-' | tr '[:upper:]' '[:lower:]')"
cat > "$fixture_root/LCUMacFixture.app/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>CFBundleIdentifier</key><string>$bundle_id</string>
<key>CFBundleExecutable</key><string>LCUMacFixture</string>
<key>CFBundleName</key><string>LCU Mac Native Fixture</string>
<key>CFBundleDisplayName</key><string>LCU Mac Native Fixture</string>
<key>CFBundlePackageType</key><string>APPL</string>
<key>LSMinimumSystemVersion</key><string>14.0</string>
</dict></plist>
PLIST
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
xcrun swiftc -O -framework AppKit "$script_dir/macos_native_fixture.swift" \
  -o "$fixture_root/LCUMacFixture.app/Contents/MacOS/LCUMacFixture"
codesign --force --sign - "$fixture_root/LCUMacFixture.app"
output="$fixture_root/draft.txt"
open -n -a "$fixture_root/LCUMacFixture.app" --args "$output"
printf 'bundle_id=%s\napp=%s\noutput=%s\n' "$bundle_id" "$fixture_root/LCUMacFixture.app" "$output"
