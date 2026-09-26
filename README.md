# LCU

LCU connects Pi, Codex CLI, and Claude Code to the pinned official ChatGPT computer-use runtime. Native computer use is the default; Chrome is opt-in and uses the original extension and site-approval flow. The original runtime owns the `cua` API, instructions, policy, and platform helpers. LCU handles installation and adapts host transport, identity, approval UI, and lifecycle wiring; it adds no replacement automation or policy layer.

## Linux quick start

Extract an architecture-matching archive on an Ubuntu 24.04-compatible desktop, then install the runtime for the existing desktop account:

~~~sh
sudo ./scripts/install.sh --user alice --runtime-only --yes
~~~

Register and launch the app-bundled Codex CLI as that account, with the same CLI on `PATH` for both commands:

~~~sh
PATH="/opt/lcu/current/app/resources:$PATH" /opt/lcu/current/bin/lcu setup --agent codex --yes
PATH="/opt/lcu/current/app/resources:$PATH" codex
~~~

Replace `alice` with the existing desktop account. For Pi, Claude Code, and offline package selection, follow the [installation guide](docs/INSTALLATION.md). See [macOS installation](docs/INSTALLATION.md#macos-and-pi); it reuses the pinned signed app in place and does not download or replace the app.

## Current verification

The current delivery targets Linux ARM64 and x86-64 plus Apple Silicon macOS. Windows is deferred from this delivery. The same-case text, PNG, WAV, and tool-error comparison is documented in [parity status](docs/PARITY-STATUS.md) and [harness adapters](docs/ADAPTERS.md). The local `dist/<source-sha>/final/DELIVERY.md` records archive hashes and gate outcomes; older results apply only to their recorded source commits. Nothing has been published.

The exact pinned Linux and macOS inputs are documented in [runtime input evidence](docs/verification/runtime-input-restoration-2026-09-26.md). The Linux app pin is ChatGPT `26.915.31945`; the signed macOS app pin is `26.917.62051`. Both contain CUA runtime `0.0.16/20260915001755-492f19756c31`. The lock file records package and component hashes. An app update requires reviewed pins before LCU will launch it.

LCU is MIT licensed. Thin archives contain LCU code and installation metadata, not OpenAI application binaries or copied upstream instructions. The installed official application keeps its original files, notices, and terms; see [dependency provenance](docs/PROVENANCE.md).
