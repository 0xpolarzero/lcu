# LCU

LCU launches the original computer-use runtime from a pinned official ChatGPT application. It preserves the original `cua` API, tool descriptions, schemas and platform instructions. Linux and Windows use verified private installations; macOS reuses the signed locally installed app in place. Thin LCU archives contain adapters and installer metadata, without OpenAI application files. The maintained harness integrations are Pi, Codex CLI and Claude Code; other harnesses can use the shared client or contribute an adapter.

**Status:** final thin archives for Linux ARM64/x86-64, Apple Silicon macOS, and Windows x64 passed source-member, payload-name, document-link, sidecar and extracted-seal audits. The Linux ARM64 and x86-64 archives also passed offline-install audits; each run passed 142 Python tests and the registration and desktop checks. See the [final archive record](docs/verification/final-four-platform-gates-2026-09-25.md) and [current status](docs/PARITY-STATUS.md) for exact artifact boundaries and limitations.

The [Pi adapter](docs/ADAPTERS.md) passed model-driven Linux native GTK and opt-in Chrome-extension tasks, including automatic temporary-tab cleanup. A compatible interactive Codex CLI also completed native and Chrome tasks, including site approval and temporary-tab cleanup. Claude Code has registration and fixture evidence only; its per-turn cleanup is not wired. These are different levels of verification, not a claim of equal harness support.

On Apple Silicon macOS, a [live TextEdit flow](docs/verification/macos-live-2026-09-24.md) passed for native typing, screenshots and saving, and a [separate opt-in Chrome action](docs/verification/chrome-opt-in-2026-09-24.md) passed through the official extension. Cold helper startup and first-time OS permissions remain unverified; the close-shortcut defect was also reproduced in the original runtime. In a disposable Windows 11 guest, installed x64 candidates passed native screenshot, typing, existing-file save, helper lifecycle, project-scoped agent registration, and an opt-in Chrome action through the official extension. The Windows Chrome check used scripted original MCP calls; Windows real-model use remains unverified. See the [parity record](docs/PARITY-STATUS.md). MCP remains the original runtime's internal transport; Pi uses its native extension API through the small shared MCP client.

## Requirements

Linux requires Ubuntu 24.04-compatible glibc on ARM64 or x86-64, Python 3.12 or newer, and an existing X11 desktop and D-Bus session owned by the target account. macOS requires Apple Silicon, Python 3.12 or newer, and the pinned signed `/Applications/ChatGPT.app` 26.917.62051. Windows 11 x64 requires Python 3.12 or newer and the pinned official `OpenAI.Codex` 26.917.9434.0 Store MSIX registered for the current account; see the [Windows installation steps](docs/INSTALLATION.md#windows-11-x64-candidate). Each platform uses its own application binaries. An app update requires reviewed pins before LCU will launch it.

The fixed dependency is ChatGPT Linux 26.915.31945 with CUA runtime 0.0.16/20260915001755-492f19756c31. [runtime.lock.json](runtime.lock.json) pins the official package URLs, hashes and critical files. Setup verifies the package before extraction. A hash checks integrity; it is not a package signature.

## Install

Build the thin archive on matching Linux first; see [development](docs/DEVELOPMENT.md). On the target desktop machine, extract it and run:

~~~sh
sudo ./scripts/install.sh --user alice --agent codex --yes
~~~

Replace alice with the existing desktop account. The installer downloads the pinned official package during setup, stores one immutable app generation under the managed prefix, selects it for LCU, and registers the agent after validation. To use an already downloaded pinned package without acquisition network access:

~~~sh
sudo ./scripts/install.sh --user alice --agent codex --app-package /absolute/chatgpt.deb --offline --skip-system --yes
~~~

Use --skip-system only when the required Ubuntu libraries are already installed. It does not skip app acquisition. For a user-owned prefix after system dependencies are in place, add --prefix and --skip-system. The installer does not change an existing system ChatGPT installation or add OpenAI's apt repository. See the [installation guide](docs/INSTALLATION.md) for agent choices, desktop sessions, rollback and failure states.

## Use

For macOS installation and Pi launch commands, see [installation](docs/INSTALLATION.md#macos-and-pi). Setup can run without prompts using explicit choices and `--yes`. macOS Screen Recording/Accessibility and unresolved browser site approvals remain the original provider's permission boundaries; `--yes` does not grant them.

Codex CLI must accept the original `mcp_tool` lifecycle hooks. Setup checks an installed CLI before changing its configuration. The tested bundled binaries are `/Applications/ChatGPT.app/Contents/Resources/codex` (`0.155.0-alpha.16.3`) on macOS and `/opt/lcu/current/app/resources/codex` (`0.155.0-alpha.9.2`) on both pinned Linux packages. The ordinary `0.145.0` CLI failed this check; no minimum public stable version has been established. Use the tested executable explicitly on `PATH` when registering and launching Codex; setup does not change your `PATH` or switch executables. See [adapter details](docs/ADAPTERS.md#codex-cli).

After setup, reconnect the agent and ask it to inspect the existing desktop. The default runtime enables native computer use and does not install or connect the Chrome extension. The generated user-local LCU skill links byte-identical original platform guidance; Chrome references are selected only for Chrome mode. The original provider supplies dynamic instructions and capability checks during use.

An agent starts with one documented call:

~~~javascript
await cua.getState();
~~~

On Linux it can then select an observed window by its ID:

~~~javascript
let app = await cua.getApp({ windowId: 123 });
~~~

The ID is an example; use a real observed ID. Screenshots, accessibility, mouse and keyboard actions, clipboard, audio paths and reset remain in the original runtime. The desktop must already be running.

To opt into Chrome, configure the agent with `lcu setup --agent codex --chrome --yes` and reconnect it. A direct MCP client must launch `lcu --chrome`. Chrome setup configures the original native host for that desktop account; to refresh its registration, run:

~~~sh
/opt/lcu/current/bin/lcu browser install
/opt/lcu/current/bin/lcu browser status
~~~

Use your intended Chrome profile; LCU does not require a new one. Install and enable the [official ChatGPT browser extension](https://learn.chatgpt.com/docs/chrome-extension) in the selected Chrome profile. `browser install` configures the native host but does not install or enable that extension. LCU does not sign in, choose a personal profile, grant site permissions, or substitute another browser. Its local native-host relay enables the official extension's `x-browser-agent` request label. The original runtime's ambient-network switch disables account identity and telemetry initialization. Site approvals remain active. The MCP client must still approve the requested site. The user and agent can view the same browser through the existing desktop viewer.

For Chrome mode, `lcu browser status` reports extension and connector configuration; it does not claim a live browser connection. Native-only setup has no extension requirement or browser-status warning. After Chrome setup, ask the configured agent to use LCU to list Chrome tabs. [Harness adapters](docs/ADAPTERS.md) describes instruction delivery, permissions, screenshots and task cleanup, including the limitations of each maintained integration.

LCU's code is [MIT licensed](LICENSE). The installed official application retains its original files, notices and terms. LCU is an independent project.
