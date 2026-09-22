# Linux parity status: 2026-09-23

**Full parity and release readiness remain unestablished.** The 0.3.0-dev candidate passed the bounded immutable Linux ARM64 and x86-64 gates recorded in [the latest evidence](verification/full-gate-1snb6f6g-2026-09-23.json). The baseline is the untouched package `26.915.31945`; the Codex app's Linux availability restriction is not a reason to remove implemented Linux features. This is not a universal parity or reliability claim.

| Area | Status and evidence |
| --- | --- |
| Application payload | Both archives retain the source-verified payload: 3,760 files and 620 directories under `/usr/lib/chatgpt`, with zero exclusions. Both checksums, offline installs, registrations and native integrations passed. |
| Runtime and instructions | Both archives pass 70 offline unit tests. All 195 instruction resources and 385 reference copies remain byte-identical to their original sources; all seven dynamic document graphs are preserved. |
| Native APIs and configuration | Both archives match 25 native cases, complete MCP schemas and delivered documentation, plus 12 configuration modes. Three native-pipe configurations match; actual connect-timeout expiration and concurrent clipboard isolation were not covered. |
| Desktop and lifecycle | ARM64 and emulated x86-64 XFCE exercises pass. Both gates pass agent-facing delivery and Stop, Interrupt and SubagentStop lifecycle cases. |
| In-app browser | Both archives pass provider, auth-failure/cache, HTTP IPC, deep-link, settings, permission, browser-command and effective-restriction checks. Authenticated external actions remain unverified. |
| Chrome and installed sandbox | Both architectures pass extension/native-host discovery, metadata boundary checks and ordinary-user installed renderer/provider startup. Browser actions require unavailable Codex authentication. |
| Find focus | Both immutable gates and a separate clean-harness run pass native browser commands with strict Ctrl+F/three-match assertions. The clean run observed focusin on the Find input. The cause of the earlier intermittent focus loss remains unproven; the recent fallback/focus-area correction has four pre-archive passes. |

The source manifest hashes the frozen archive inputs. Subsequent edits to documentation and `tests/iab_commands.cjs` are outside those archives; production source and instructions still match the captured tree. The clean Find run used the frozen archives and a separately hashed test harness. Its initial x64 bootstrap errors are preserved and did not reach the fixture. Initial production-sandbox probes also failed on a fixture path; corrected VM-only retries passed, and both failures remain recorded.

## Remaining blockers

- Authenticated browser actions and CDP/cloud/Orbit providers depend on external identity, account, server and broker inputs that were not available. Resolved account/rollout features and translation catalogs also require their managing-host sources.
- A real managing-host event stream and stable reconnect identity remain external inputs. Their end-to-end integration and generic-agent enforcement of the exported host contract remain unverified.
- Automatic approval review rejected broadening `NODE_REPL_TRUSTED_CODE_PATHS` to all of `CODEX_HOME`; the narrower roots remain.

The original native verification app service is Darwin-gated and has no normal Linux caller; this is an evidenced platform boundary, not a missing Linux feature. Tests did not fabricate approval responses. x86-64 ran under emulation on Apple Silicon, so these results do not establish behavior on native x86-64 hardware.

The evidence covers these fixtures and inputs only. It does not establish universal behavioral identity, agent reliability, or release readiness. See [INVENTORY.md](INVENTORY.md), [HOST-INVENTORY.md](HOST-INVENTORY.md), [INSTRUCTIONS.md](INSTRUCTIONS.md), [STANDALONE-ADAPTATIONS.md](STANDALONE-ADAPTATIONS.md), and [BROWSER-DEPENDENCIES.md](BROWSER-DEPENDENCIES.md) for source and dependency audits.

Earlier candidate failures and their actual coverage remain recorded in [lc0e4isg](verification/full-gate-lc0e4isg-2026-09-22.json), [4djwlqe0](verification/full-gate-4djwlqe0-2026-09-22.json), and [hxkg3p_6](verification/full-gate-hxkg3p_6-2026-09-22.json).
