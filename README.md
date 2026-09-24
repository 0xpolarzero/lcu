# LCU

LCU launches the original computer-use runtime from a pinned official ChatGPT application. It preserves the original `cua` API, tool descriptions, schemas and platform instructions. Linux uses a verified private installation; macOS reuses the signed locally installed app in place. Thin LCU archives contain adapters and installer metadata, without OpenAI application files.

**Status:** native computer use and the thin installed-app path passed the offline differential checks. The installed ARM64 and x86-64 builds passed no-sign-in Chrome actions in Ubuntu 24.04.5 guests with AppArmor active; the x86-64 guest ran under KVM on physical AMD hardware. LCU installs a small native-host relay that enables the official extension's `x-browser-agent` header locally. The original package's AppArmor profile targets its Electron UI, not LCU's Node/REPL executable. See [current status](docs/PARITY-STATUS.md) for exact evidence and limitations.

The macOS Apple Silicon path and [Pi adapter](docs/ADAPTERS.md) are under validation. A [live TextEdit flow](docs/verification/macos-live-2026-09-24.md) passed for native typing, screenshots and saving. Cold helper startup and Chrome actions remain unverified; one close shortcut behaved unexpectedly. Windows is not implemented. MCP remains the original runtime's internal transport; Pi uses its native extension API through the small shared MCP client.

## Requirements

Linux requires Ubuntu 24.04-compatible glibc on ARM64 or x86-64, Python 3.12 or newer, and an existing X11 desktop and D-Bus session owned by the target account. macOS requires Apple Silicon, Python 3.12 or newer, and the pinned signed `/Applications/ChatGPT.app` 26.917.62051. Each platform uses its own application binaries. An app update requires reviewed pins before LCU will launch it.

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

After setup, reconnect the agent and ask it to inspect the existing desktop. The generated user-local LCU skill links byte-identical original platform and Chrome guides before the first tool call. The original provider supplies dynamic instructions and capability checks during use.

An agent starts with one documented call:

~~~javascript
await cua.getState();
~~~

On Linux it can then select an observed window by its ID:

~~~javascript
let app = await cua.getApp({ windowId: 123 });
~~~

The ID is an example; use a real observed ID. Screenshots, accessibility, mouse and keyboard actions, clipboard, audio paths and reset remain in the original runtime. The desktop must already be running.

Agent setup configures the original native host for that Linux account. To refresh its registration, run:

~~~sh
/opt/lcu/current/bin/lcu browser install
~~~

Install and enable the [official ChatGPT browser extension](https://learn.chatgpt.com/docs/chrome-extension) in the selected Chrome profile. LCU does not sign in, choose a personal profile, grant site permissions, or substitute another browser. Its local native-host relay enables the official extension's `x-browser-agent` request label, so the original browser service can act without the Codex account feature-gate lookup. The MCP client must still approve the requested site. The user and agent can view the same browser through the existing desktop viewer.

Agent hosts need MCP site-approval support for Chrome. Goose 1.51.0 can use the opt-in `--mcp-discovery-compat` flag in an interactive session; see [installation](docs/INSTALLATION.md). OpenCode 1.18.32 did not provide site approval in the tested mode, so its browser action stopped before loading the page.

LCU's code is [MIT licensed](LICENSE). The installed official application retains its original files, notices and terms. LCU is an independent project.
