# Final four-platform archive gate (2026-09-25)

The four thin archives were built from clean source commit
`66bb0fb0dd2235dd83ab35e7ac468a985fc0b77f`. The immutable outputs are under
`dist/66bb0fb0dd2235dd83ab35e7ac468a985fc0b77f/` in the project checkout.
All four builds completed. The member audit found no first-party source
mismatches or missing source files, upstream payload names, or broken installed
document links. Each archive's SHA-256 sidecar matched, and each extracted
bundle passed its seal check.

| Archive | SHA-256 |
| --- | --- |
| `linux-arm64/lcu-0.3.0-linux-arm64.tar.gz` | `bcb47d9619cfe039dfbe48155e72ca0c85b59871e18e8c307a3e3a8542762d1f` |
| `linux-x64/lcu-0.3.0-linux-x64.tar.gz` | `629b8b5a57b0cf6959a2da0aa29d33a4f077d0ee0178bd88af331dc398bb0c9d` |
| `darwin-arm64/lcu-0.3.0-darwin-arm64.tar.gz` | `a56cc54b0c45d214391c349e4a161d7458c090c246db159d670344ad3b0392bd` |
| `windows-x64/lcu-0.3.0-windows-x64.zip` | `f5b66fe303999cd24703ca33c003e0d35ad918c0805ac9edd1ce6b7d06908d67` |

The Linux offline archive gates did not complete. Both supplied disposable
containers verified their archive sidecars, then Docker ended with exit 125
and `error waiting for container: unexpected EOF`. Read-only status later
reported OrbStack `Stopped`; after one normal app launch, the app process was
present but its Docker API socket remained absent. No test assertion failure
was observed. The exact failure and engine state are preserved in
`/private/tmp/lcu-final-offline-gate-failure-66bb0fb.txt`.

Earlier implementation evidence is separate from these four archives: 142
ordinary tests passed in the ARM64 container. Historical `b11ae52` Linux
archives had their own 120-test offline gates, recorded in
[the earlier archive report](final-linux-gates-2026-09-24.md). Neither result
proves the final archives' offline installation behavior.

Live platform evidence also has separate boundaries. macOS cold helper startup
and first-time permissions remain unverified. Windows candidate f passed the
documented native, setup and official-extension checks, but Windows model use
and automatic browser per-turn cleanup remain unverified. Claude Code's
per-turn lifecycle hooks remain unwired. These archive builds are local
verification artifacts, not published releases.
