# Verification: 2026-09-22

The installed standalone MCP command operated independent Linux GUI fixtures successfully on ARM64 and x86-64. Tests used Ubuntu 24.04 containers, Xvfb, Openbox, a session D-Bus, GTK 3/AT-SPI, and an Xlib window without accessibility. ARM64 ran natively on an Apple Silicon Docker host; x86-64 ran under the host's emulation. No personal desktop, agent credentials, or app login was used.

## Results

| Check | Result |
| --- | --- |
| Original MCP initialization and four advertised tools | Passed on both architectures |
| Correct Linux window-ID instructions and first-use documentation | Passed on both |
| AT-SPI discovery, bound element clicks, Unicode text | Passed on both |
| Key combinations, native paste, advertised secondary action | Passed on both |
| Independent GTK saved-file oracle | Passed on both |
| Two same-process windows; other window remains unchanged | Passed on both |
| X11 fallback observation and JPEG screenshot | Passed on both |
| Window-relative coordinate input | Passed on both; Xlib event oracle received exactly `40,40` |
| Unsupported methods and malformed input return errors | Passed on both |
| Persistent variables, reset, documentation replay | Passed on both |
| Execution timeout and recovery | Passed on both; deliberate timeout emits an expected diagnostic |
| Desktop doctor and subsequent MCP connection | Passed |
| Install/registration without a desktop | Passed |
| Complete online install as a non-root account | Passed on ARM64 |
| Full desktop suite as that non-root account | Passed on ARM64 |
| Seven agent registrations, user and project scopes | Passed |
| Target-account ownership, idempotency, unrelated configuration values | Passed |
| Malformed existing JSONC preserved; setup reports failure | Passed |
| Portable MCP plus skill export | Passed |
| Invalid installer arguments cause no installation writes | Passed |
| Corrupt official package leaves active release selected | Passed |
| Twelve installation/session regression tests | Passed |
| Skill validation and shell/Python syntax checks | Passed |
| One-command fresh-container workflow | Passed on x86-64 |

The one-command workflow was run with `tests/run.sh linux/amd64 /absolute/chatgpt_amd64.deb`. Both architectures also ran the installer and `dbus-run-session -- bash tests/desktop.sh` individually. ARM64 additionally installed from the pinned network URL under an ordinary account and ran that account's installed MCP command against the same desktop fixtures.

Regression tests cover conflicting session discovery, rejecting another user's session, copying only GUI environment variables, preserving sandbox/approval settings, corrupt downloads, unknown source shapes, reordered platform dispatch, symlink/foreign/relative installation prefixes, concurrent configuration edits, and upgrade failure cleanup.

## Size and fingerprints

Measured with `du -sh` after installation. ARM64: 148 MiB runtime plus 8.2 MiB agent setup dependencies. x86-64: 153 MiB runtime plus 8.2 MiB agent setup dependencies. Desktop libraries and temporary build/download space are additional. Installation downloads the complete official package (about 396 MB ARM64 or 417 MB x86-64) and needs roughly 2 GB of temporary disk space.

| Installed binary | ARM64 SHA-256 | x86-64 SHA-256 |
| --- | --- | --- |
| Node | `0f8949d1028f6d61506b2d5bc57e7e6fe893d7b1997509b7847294fc9c616584` | `7fde7b8afa198da66257f42ee2001d874c7355631e6d1579a5fb5ef1f246df4c` |
| Node REPL | `dd56678070aae3788052b79b62a145c279c61fcd3e9f7d9613905f2b4972a931` | `a42e393a4e1332014275ca64f41e5ce80137d32d57a24658e568fe5ab9ada3f9` |
| Sky Linux engine | `e60f50bf7239963fac6d725a41044de04bc96c6eca224a5016880fa12fbb0f8c` | `6d6971a8d09fa1c932587442d771c8beaf41b75e2a1e25e098b6112b46a691ad` |

## Limits of this evidence

This proves standalone execution through the original MCP REPL against real test applications, plus installer behavior. It does not establish task-success parity with Codex on macOS, evaluate seven different agent models, or prove compatibility with arbitrary Linux applications.

Native Wayland, musl, other distributions, production Silo guests, real XFCE discovery, multiple simultaneous agents, optional audio methods, drag behavior, and successful scrolling in a complex app were not exercised. XFCE discovery was tested with deterministic process fixtures. Scroll argument rejection was exercised. These paths retain the original implementation where applicable; no replacement was added to conceal missing evidence.

The upstream registration tools preserve configuration values but can rewrite formatting and comments. The initial test expected TOML comments to survive; inspection showed that upstream normalizes them. The final test checks preserved values and idempotent registration, and the README discloses the formatting behavior.
