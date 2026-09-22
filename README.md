# cual

Computer use agent Linux: the shipped Codex Linux computer-use runtime, packaged as a standalone MCP server.

Cual uses OpenAI's original Linux Sky executable, Node REPL, trusted-service protocol, and Linux `cua` implementation. It adds installation, desktop-session selection, agent registration, and Linux-only instructions. It contains no replacement desktop automation engine.

The installer downloads an exact official OpenAI package, verifies its checksum, extracts the runtime without installing the desktop app, and removes the other platform and browser-provider implementations. The repository contains packaging code and instructions; OpenAI's runtime is an external dependency, not vendored or relicensed here. See [provenance and boundaries](docs/PROVENANCE.md).

## Install

Run from this checkout **inside the Linux machine whose desktop will be controlled**:

```sh
sudo ./scripts/install.sh --user alice --agent codex --yes
```

Requirements: Linux ARM64 or x86-64, Python 3.12+, a glibc system, X11, and a D-Bus desktop session. Ubuntu 24.04 is tested. Automatic system provisioning uses apt. Other distributions need equivalent libraries plus `dpkg-deb`, then `--skip-system`; they are not yet verified. Native Wayland and musl are not supported by this release.

Cual does not install a desktop, start a login session, install an agent, or authenticate one. Installation and registration work during image builds without a running GUI.

```sh
# Select several agents, or all seven supported clients.
sudo ./scripts/install.sh --user alice --agent codex --agent claude-code --yes
sudo ./scripts/install.sh --user alice --agent all --yes

# Bake the runtime into an image; register agents later.
sudo ./scripts/install.sh --user alice --runtime-only --yes
/opt/cual/current/bin/cual setup --agent codex --yes

# Install as the desktop account after provisioning system dependencies.
./scripts/install.sh --prefix "$HOME/.local/share/cual" --skip-system --agent codex --yes

# An agent already running inside an X11 desktop can inherit its environment.
./scripts/install.sh --prefix "$HOME/.local/share/cual" --skip-system --agent codex --session direct --yes
```

The installer retains Luda's `--prefix`, `--user`, repeated `--agent`, `all`, `auto`, `--list-agents`, `--scope`, `--project`, `--export`, `--check-desktop`, `--session`, `--yes`, `--runtime-only`, `--skip-system`, and legacy positional-prefix interface. Root must select an account explicitly. Automated installs must explicitly select agents, export, or runtime-only mode. `--browser-config` is deliberately absent because this package has no separate browser provider.

`--session discover` is the default. Each launch finds exactly one existing XFCE session belonging to the calling account and copies only its GUI connection variables. It rejects ambiguous sessions. For other X11 desktops, use `--session direct` and provide `DISPLAY`, `DBUS_SESSION_BUS_ADDRESS`, and any required `XAUTHORITY` in the agent's environment.

## Agents

Built-in registration supports Codex, Claude Code, Cursor, Gemini CLI, OpenCode, VS Code, and Copilot CLI. Aliases `claude`, `gemini`, and `copilot` also work. The client executable need not exist during registration. Upstream `skills` and `add-mcp` installers own client formats; unrelated configuration values are preserved, though upstream formatters can rewrite comments and formatting.

```sh
/opt/cual/current/bin/cual setup --list-agents
/opt/cual/current/bin/cual setup --agent cursor --scope project --project /absolute/project --yes
/opt/cual/current/bin/cual setup --export /absolute/new/cual-plugin --yes
```

Exports contain an MCP configuration and `skills/cual/SKILL.md`. Any agent with stdio MCP and image support can connect to the command below. This is protocol compatibility, not a claim that every agent/model has been evaluated.

```json
{
  "mcpServers": {
    "cual": {
      "command": "/opt/cual/current/bin/cual-session",
      "args": ["--user", "alice", "--", "/opt/cual/current/bin/cual"]
    }
  }
}
```

For direct mode, use `/opt/cual/current/bin/cual` with no arguments. Restart or reconnect the agent after registration. The original REPL exposes `js`, `js_reset`, `js_add_node_module_dir`, and its `turn_ended` notification tool. The skill routes the agent to the runtime's Linux API documentation.

First tool call:

```javascript
await cua.listWindows();
```

Then select an observed window ID:

```javascript
let app = await cua.getApp({ windowId: 123 });
```

Observe the returned accessibility state, perform the intended actions, and observe again. See the [Linux API instructions](instructions/api/tinysky-alt-core-cua-repl.md).

## Check, upgrade, and rollback

```sh
/opt/cual/current/bin/cual-session --user alice -- /opt/cual/current/bin/cual doctor
```

`doctor` checks the inherited desktop connection and asks the original engine for its window inventory. An empty inventory means the connection worked but no windows were found; it does not prove accessibility or input works in every app.

Rerun the installer to install a new version. It builds a separate release and atomically changes `current` only after validation. Failed downloads and builds leave the previous release selected. Old releases remain available. To roll back, select the intended directory under `releases` and atomically replace the `current` symlink; restart connected MCP clients afterward. No automatic runtime updates happen during agent use.

`--package /absolute/chatgpt_arm64.deb` or its x86-64 counterpart uses a locally cached official package with the same mandatory checksum. Installer dependencies still require network access. [runtime.lock.json](runtime.lock.json) pins the OpenAI version and esbuild downloads; agent installers have a separate npm lockfile. Unknown package hashes and unexpected source shapes fail closed.

## Runtime boundaries

Install and run Cual as the desktop account inside the intended VM or sandbox. Cual is not itself a sandbox: the standalone REPL runs with that account's permissions. Existing Codex sandbox and approval settings are preserved when supplied by the host. The original confirmation-policy handling remains in the runtime. Cual disables REPL analytics by default and never installs agent credentials.

The original compiled REPL and native engine are retained intact. JavaScript is specialized to Linux and bundled, with build input manifests recording the retained modules. Dedicated browser providers, other platform engines, and their instructions are excluded. Browser windows remain ordinary Linux windows.

The official Linux app preview does not yet advertise Computer Use as an enabled feature. Cual relies on a shipped implementation verified independently, not a supported standalone OpenAI SDK. [Official platform status](https://learn.chatgpt.com/docs/linux/linux-app#compatibility-and-limitations).

## Verify

The tests use disposable Docker containers and independent GTK/Xlib applications. No personal desktop or agent account is accessed.

```sh
./tests/run.sh linux/arm64
./tests/run.sh linux/amd64
# Optional cached official package, still checksum-verified:
./tests/run.sh linux/arm64 /absolute/chatgpt_arm64.deb
```

See [verification results](docs/VERIFICATION.md) for exactly what passed and what remains untested.

## License

Cual's original packaging code and Luda-derived installation code are MIT licensed. OpenAI's downloaded runtime and its dependencies retain their own terms and notices. This repository grants no rights to redistribute or relicense those files. It is an independent project, not an OpenAI release.
