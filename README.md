# LCU

LCU connects Pi, Codex CLI, and Claude Code to the official ChatGPT computer-use runtime. Install the current ChatGPT desktop app with Codex before installing LCU; LCU never downloads or installs the app. If it is missing, [download ChatGPT](https://chatgpt.com/download/) and install it first. Native computer use is the default; Chrome is opt-in and uses the original extension and site-approval flow. The original runtime owns the `cua` API, instructions, policy, and platform helpers. LCU handles installation and adapts host transport, identity, approval UI, and lifecycle wiring; it adds no replacement automation or policy layer.

## Linux quick start

Extract an architecture-matching archive on an Ubuntu 24.04-compatible desktop, then install the runtime for the existing desktop account:

~~~sh
sudo ./scripts/install.sh --user alice --runtime-only --yes
~~~

Register and launch the app-bundled Codex CLI as that account, with the same CLI on `PATH` for both commands:

~~~sh
PATH="/opt/lcu/current/app/resources/codex-cli/bin:/opt/lcu/current/app/resources:$PATH" /opt/lcu/current/bin/lcu setup --agent codex --yes
PATH="/opt/lcu/current/app/resources/codex-cli/bin:/opt/lcu/current/app/resources:$PATH" codex
~~~

Replace `alice` with the existing desktop account. Linux uses the existing app at `/usr/lib/chatgpt` by default; pass `--existing-app /absolute/path` to select another installed app. LCU makes a private managed copy and leaves the installed app in place. For Pi, Claude Code, macOS, and alternate app paths, follow the [installation guide](docs/INSTALLATION.md). Agent selection is explicit: `--agent all` configures Pi, Codex CLI, and Claude Code; `--agent auto` configures detected agents; omitting `--agent` opens an interactive chooser. Noninteractive agent setup requires an explicit selection; use `--runtime-only` to install without registering an agent.

## Current verification

The current delivery targets Linux ARM64 and x86-64 plus Apple Silicon macOS. Windows is deferred from this delivery. The same-case text, PNG, WAV, and tool-error comparison is documented in [parity status](docs/PARITY-STATUS.md) and [harness adapters](docs/ADAPTERS.md). The local `dist/<source-sha>/final/DELIVERY.md` records archive hashes and gate outcomes; older results apply only to their recorded source commits. Nothing has been published.

App selection checks supported platform and architecture, official identity and signatures where applicable, the runtime manifest, required files, and the recognized original host layout. LCU records the selected app and runtime versions; managed private copies are protected by an inventory derived from that selected source. It does not use repository app-version or component-hash allowlists. The current macOS check accepted signed ChatGPT `26.924.22138` with CUA runtime `0.0.24/20260924074400-f52ea85e2a98`; see [current-app verification](docs/verification/macos-current-app-2026-09-26.md). `runtime.lock.json` retains historical source metadata and a package checksum; LCU does not use these to download or select an app.

LCU is MIT licensed. Thin archives contain LCU code and installation metadata, not OpenAI application binaries or copied upstream instructions. The installed official application keeps its original files, notices, and terms; see [dependency provenance](docs/PROVENANCE.md).
