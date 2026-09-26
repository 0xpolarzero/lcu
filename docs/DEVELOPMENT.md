# Development and validation

LCU releases are thin platform/architecture-specific archives: Linux and macOS tarballs, plus a Windows ZIP. The official app is never part of an archive. Local app selection checks official identity/signature where applicable, supported architecture, runtime manifest, required files, and recognized host layout; it records the observed app and runtime versions instead of requiring repository app-version or component-hash allowlists. macOS uses the signed installed app in place. Linux accepts local packages/apps by package identity, architecture, structure, and managed-tree integrity; the default remote download still uses the URL and checksum in [runtime.lock.json](../runtime.lock.json). Windows selects the registered official Store app and records a source-derived inventory for its private copy. The lock file retains historical source metadata and the default Linux acquisition checksum, not a cross-platform compatibility gate.

## Build

Use Python 3.12+ on matching Linux ARM64 or x86-64:

~~~sh
python3 scripts/build_bundle.py --output dist
~~~

The builder creates a tarball and SHA-256 sidecar. It provisions the fixed third-party agent registration tools and links their Node executable to the application that setup selects later. It does not download or extract the OpenAI app. Build-time --package is retired; pass --app-package to scripts/install.sh on the target machine.

The Windows x64 ZIP is built with `python3 scripts/build_bundle.py --platform windows --output dist`. It contains no OpenAI payload. Direct execution from the protected WindowsApps tree returned Access denied, and the original sandboxed Node REPL could not spawn the native helper directly. The installer stages an intact copy of the registered Store-signed application, records and checks its source-derived inventory, and extracts the required original `Wre` pipe host outside that sandbox. It does not use the inspected package version or component hashes as compatibility gates. Installed candidates in a disposable Windows 11 guest initialized the original MCP, listed a live Notepad window, and saved exact Unicode text to an existing file with an independent byte oracle. A matching Stop and Interrupt each removed the native helper; a stale Stop left a newer turn's helper running, and MCP shutdown removed the final helper. These observations establish installed native action and lifetime behavior, not a Windows Chrome or model-driven task. The [live Windows record](verification/windows-source.md) gives the guest boundaries.

Claude Code registration on Windows does not supply original per-turn cleanup. Its documented [`Stop` hook](https://code.claude.com/docs/en/hooks) excludes user interruption, while `StopFailure` covers API errors and `SessionEnd` fires only when the session ends. Until a supported ordinary-CLI interruption event and matching turn metadata are validated, use Pi or a compatible Codex CLI for Windows native work that needs automatic per-turn helper cleanup; the same recommendation applies to optional Chrome temporary-tab cleanup.

On supported Apple Silicon macOS, with a compatible official app already installed and `npm` available:

~~~sh
python3 scripts/build_bundle.py --platform darwin --app /Applications/ChatGPT.app --output dist
~~~

Both archives include the same shared MCP SDK client and Pi extension. The macOS archive adds only app resolution, signature validation and installation dispatch. Selection reads actual app/runtime metadata and supports the legacy and current recognized Codex tool locations; supported architecture remains Apple Silicon. The builder uses the verified app's Node and the host's npm CLI to install locked registration and adapter dependencies. It does not install or alter the app.

Run adapter checks with `npm test --prefix adapters`. [Mac runtime verification](verification/macos-runtime.md) distinguishes transport/instruction checks from live native control. A sandbox that prevents `codesign` reading signing services or prohibits nested `sandbox-exec` cannot perform those checks; preserve original sandbox settings and run verification in an appropriate host environment.

Before publishing, inspect the tar member list and unpacked tree. They must contain LCU-owned launchers, wrapper skill, lock/installer metadata and redistributable registration dependencies only. They must not contain app binaries, upstream instruction copies, generated app fragments, profiles or tokens. Portable exports have the same no-OpenAI-payload requirement.

## Install and exercise an isolated fixture

Prepare a disposable Ubuntu 24.04-compatible Linux desktop and account, and use a verified local official .deb:

~~~sh
./scripts/install.sh --prefix /absolute/test-prefix --user testuser --skip-system --app-package /absolute/chatgpt.deb --offline --runtime-only --yes
/absolute/test-prefix/current/bin/lcu doctor
~~~

Root is required only for apt and another account's setup; the target app/REPL must be exercised as that unprivileged desktop account. Use an isolated HOME, CODEX_HOME, X11 session and browser profile. Keep the untouched original package baseline independent of LCU helpers, then compare observable GTK/X11/file/clipboard outcomes. Do not count a matching failure, tools/list, browser inventory or extension discovery as a successful browser action.

Run focused unit checks during implementation:

~~~sh
python3 -m unittest discover -s tests -p 'test_runtime.py'
python3 -m unittest discover -s tests -p 'test_instructions.py'
python3 -m unittest discover -s tests -p 'test_installation.py'
~~~

The final gate must test both architectures, mark emulation explicitly, and run native and Chrome actions under a normal Ubuntu host policy outside a privileged container. Inspect the actual process confinement labels and policy denials; the ChatGPT Electron profile is not a prerequisite for LCU's direct Node/REPL path. The [ARM64 and x86-64 Ubuntu AppArmor host runs](verification/installed-app-2026-09-23.md) passed native use and no-sign-in Chrome actions with actual process labels. The x86-64 guest used KVM on physical AMD hardware. Docker fixtures alone prove bounded native behavior and offline failure paths, not host OS confinement.

Chrome verification uses the original MCP → browser service → LCU relay → original native host → extension chain and an isolated Chrome profile. The target path must complete navigation, input, click, screenshot and lifecycle without Codex sign-in, and the fixture server must observe `x-browser-agent` on the requests. The original browser also requests scoped MCP site approval; a test client may approve its own disposable localhost fixture, but must not synthesize a broader grant. Never copy a personal credential store. The [current status](PARITY-STATUS.md) distinguishes this local policy override from the original Codex account policy.

Historical IAB fixture and full-copy bundle evidence predates this migration. [Verification](VERIFICATION.md) and [current status](PARITY-STATUS.md) separate those results from final thin-artifact claims.
