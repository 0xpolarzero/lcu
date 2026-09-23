# Development and validation

LCU releases are thin architecture-specific tarballs. The official ChatGPT Linux app is acquired on the target Linux machine during installation and is never part of the archive. [runtime.lock.json](../runtime.lock.json) pins app 26.915.31945, runtime 0.0.16/20260915001755-492f19756c31, package SHA-256 values and critical component hashes.

## Build

Use Python 3.12+ on matching Linux ARM64 or x86-64:

~~~sh
python3 scripts/build_bundle.py --output dist
~~~

The builder creates a tarball and SHA-256 sidecar. It provisions the fixed third-party agent registration tools and links their Node executable to the application that setup selects later. It does not download or extract the OpenAI app. Build-time --package is retired; pass --app-package to scripts/install.sh on the target machine.

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
