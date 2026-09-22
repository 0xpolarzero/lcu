# LCU

**The upstream Codex Linux computer-use runtime, packaged for standalone agents.**

LCU (Linux Computer Use) bundles the complete original Linux runtime, public JavaScript exports, instructions, browser libraries, native host, and companion Codex executables. It runs on your Linux machine or VM and exposes the original persistent MCP JavaScript interface.

**This is an unfinished `0.3.0-dev` parity build.** Native desktop operations work independently without an OpenAI account. The original browser provider requires Codex authentication for actions. The standalone in-app-browser host is under integration testing. Authenticated host services, cloud/Orbit providers and generic-agent lifecycle integration remain unresolved. See the [capability and dependency inventory](docs/INVENTORY.md) and [browser host status](docs/BROWSER-HOST-PARITY.md). No full-parity release is claimed.

## API

Your agent calls the `js` MCP tool with JavaScript. Variables persist between calls.

First, list the open windows. This read-only call also returns the API instructions. The same [full guide](skills/lcu/references/api.md) is available before any tool call:

```javascript
await cua.listWindows();
```

In the next call, select a window using its returned ID:

```javascript
let app = await cua.getApp({ windowId: 123 });
```

Selection returns the window's controls and their IDs. Click a text field, type, then read the updated window:

```javascript
await app.click(2);
await app.typeText("Hello from LCU");
await app.getAXState();
```

`123` and `2` are examples. Use the window and control IDs from your actual observations.

For apps without accessible controls, take a screenshot and use coordinates relative to the window:

```javascript
await app.getScreenshot();
```

Then choose a position from the screenshot and call `app.click([x, y])`. The API also supports keyboard shortcuts, paste, drag, and scrolling. See the [API reference](instructions/api/tinysky-alt-core-cua-repl.md) for arguments and examples.

## Install

Install **on the Linux machine whose desktop the agent will control**. You need Python 3.12+ and an existing X11 desktop. Ubuntu 24.04 is tested. Native Wayland is not supported.

Build the development archive using the [build instructions](docs/DEVELOPMENT.md). The published [v0.2.1](https://github.com/0xpolarzero/lcu/releases/tag/v0.2.1) is the earlier native-only subset and does not contain this branch's restored features.

In the download directory, run the following. Change `x64` to `arm64` for ARM64:

```sh
archive=lcu-0.3.0-dev-linux-x64.tar.gz
sha256sum -c "$archive.sha256" &&
  tar -xzf "$archive" &&
  cd "${archive%.tar.gz}" &&
  sudo ./scripts/install.sh --user "$(id -un)" --agent codex --yes
```

Run this as your desktop user. If you are already root, replace `$(id -un)` with that user's name.

The installer adds the tools and skill to your agent's configuration. Restart or reconnect the agent, then ask: **“Use LCU to inspect my desktop.”**

The runtime and original host executables are included in the archive. The installer uses apt for system libraries; add `--skip-system` if they are already installed. Default setup connects to your XFCE session. For another X11 desktop, use [`--session direct`](docs/INSTALLATION.md#connect-to-a-desktop).

The experimental bundled in-app-browser host is explicit: register with `--browser-host`, or launch `lcu --with-browser-host`. This requires a graphical, non-root account and retains the original authentication and policy checks. See the [adaptation ledger](docs/STANDALONE-ADAPTATIONS.md).

For the external-browser provider, run `lcu browser install` as the browser's Linux account, then enable the official ChatGPT browser extension. This uses the original native messaging installer. Browser actions retain upstream authentication and policy requirements; [connection and host requirements](docs/BROWSER-HOST-PARITY.md) explain the current limits.

## Agents

Use `--agent codex`, `claude-code`, `cursor`, `gemini-cli`, `opencode`, `vscode`, or `copilot-cli`. Repeat `--agent` to select several, or use `--agent all`. Omit `--agent` and `--yes` for an interactive choice.

Other agents can use the [MCP configuration and skill export](docs/INSTALLATION.md#other-agents). The [skill](skills/lcu/SKILL.md) links complete, unchanged upstream guides before the first call. Codex registration also installs the original tool filtering, routing, startup timeout, output allowance and exact lifecycle hooks. Portable export includes native Codex plugin files and tool/lifecycle contracts; another agent must honor those contracts for equivalent host behavior.

## More

- [Installation guide](docs/INSTALLATION.md): desktop sessions, VM images, custom agents, upgrades, and migration from Cual.
- [API reference](instructions/api/tinysky-alt-core-cua-repl.md): methods, parameters, and examples.
- [Development](docs/DEVELOPMENT.md): build and test a release.
- [Test results](docs/VERIFICATION.md): what has been checked and known limits.
- [Instruction fidelity](docs/INSTRUCTIONS.md): complete upstream text, zero runtime instruction edits, and delivery checks.
- [Runtime sources](docs/PROVENANCE.md): where the bundled code comes from.

LCU controls an existing desktop and runs with your Linux account's permissions. Use your VM or container to isolate it. Application support depends on accessibility; screenshots and coordinates are available when controls cannot be read.

LCU's own code is [MIT licensed](LICENSE). The bundled runtime and dependencies keep their own terms and notices. LCU is an independent project, not an official OpenAI release.
