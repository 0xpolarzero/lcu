# LCU

Linux Computer Use: the shipped Codex Linux computer-use runtime, packaged as a standalone MCP server.

LCU uses OpenAI's original Linux Sky executable, Node REPL, trusted-service protocol, and Linux `cua` implementation. It adds installation, desktop-session selection, agent registration, and Linux-only instructions. It contains no replacement desktop automation engine.

Release archives bundle the Linux engine, Node, the original REPL, projected JavaScript, agent-registration dependencies, instructions, and upstream notices. Installation verifies and copies those local files. It never downloads the runtime, invokes npm, or rebuilds computer use. Maintainers fetch pinned inputs when building a release. See [provenance and boundaries](docs/PROVENANCE.md).

## Install

Extract the archive for your architecture **inside the Linux machine whose desktop will be controlled**:

```sh
sha256sum -c lcu-0.2.0-linux-arm64.tar.gz.sha256
tar -xzf lcu-0.2.0-linux-arm64.tar.gz
cd lcu-0.2.0-linux-arm64
sudo ./scripts/install.sh --user alice --agent codex --yes
```

Requirements: Linux ARM64 or x86-64, Python 3.12+, a glibc system, X11, and a D-Bus desktop session. Ubuntu 24.04 is tested. Automatic system provisioning uses apt. Other distributions need equivalent libraries, then `--skip-system`; they are not yet verified. Native Wayland and musl are not supported by this release.

For x86-64, use the `linux-x64` archive. With system dependencies already present, `--skip-system` makes installation and agent registration fully offline. Without that flag, apt can install missing operating-system libraries.

LCU does not install a desktop, start a login session, install an agent, or authenticate one. Installation and registration work during image builds without a running GUI.

```sh
# Select several agents, or all seven supported clients.
sudo ./scripts/install.sh --user alice --agent codex --agent claude-code --yes
sudo ./scripts/install.sh --user alice --agent all --yes

# Bake the runtime into an image; register agents later.
sudo ./scripts/install.sh --user alice --runtime-only --yes
/opt/lcu/current/bin/lcu setup --agent codex --yes

# Install as the desktop account after provisioning system dependencies.
./scripts/install.sh --prefix "$HOME/.local/share/lcu" --skip-system --agent codex --yes

# An agent already running inside an X11 desktop can inherit its environment.
./scripts/install.sh --prefix "$HOME/.local/share/lcu" --skip-system --agent codex --session direct --yes
```

The installer retains Luda's `--prefix`, `--user`, repeated `--agent`, `all`, `auto`, `--list-agents`, `--scope`, `--project`, `--export`, `--check-desktop`, `--session`, `--yes`, `--runtime-only`, `--skip-system`, and legacy positional-prefix interface. Root must select an account explicitly. Automated installs must explicitly select agents, export, or runtime-only mode. `--browser-config` is deliberately absent because this package has no separate browser provider.

`--session discover` is the default. Each launch finds exactly one existing XFCE session belonging to the calling account and copies only its GUI connection variables. It rejects ambiguous sessions. For other X11 desktops, use `--session direct` and provide `DISPLAY`, `DBUS_SESSION_BUS_ADDRESS`, and any required `XAUTHORITY` in the agent's environment.

## Agents

Built-in registration supports Codex, Claude Code, Cursor, Gemini CLI, OpenCode, VS Code, and Copilot CLI. Aliases `claude`, `gemini`, and `copilot` also work. The client executable need not exist during registration. Upstream `skills` and `add-mcp` installers own client formats; unrelated configuration values are preserved, though upstream formatters can rewrite comments and formatting.

```sh
/opt/lcu/current/bin/lcu setup --list-agents
/opt/lcu/current/bin/lcu setup --agent cursor --scope project --project /absolute/project --yes
/opt/lcu/current/bin/lcu setup --export /absolute/new/lcu-plugin --yes
```

Exports contain an MCP configuration and `skills/lcu/SKILL.md`. Any agent with stdio MCP and image support can connect to the command below. This is protocol compatibility, not a claim that every agent/model has been evaluated.

```json
{
  "mcpServers": {
    "lcu": {
      "command": "/opt/lcu/current/bin/lcu-session",
      "args": ["--user", "alice", "--", "/opt/lcu/current/bin/lcu"]
    }
  }
}
```

For direct mode, use `/opt/lcu/current/bin/lcu` with no arguments. Restart or reconnect the agent after registration. The original REPL exposes `js`, `js_reset`, `js_add_node_module_dir`, and its `turn_ended` notification tool. The skill routes the agent to the runtime's Linux API documentation.

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

LCU was named Cual in v0.1.0. To migrate, install this release into the new default `/opt/lcu` prefix and register your agents again. Remove the old `cual` MCP entry and skill from those agents, then restart them. The old installation is left in place; the new installer does not rewrite its files or registrations.

```sh
/opt/lcu/current/bin/lcu-session --user alice -- /opt/lcu/current/bin/lcu doctor
```

`doctor` checks the inherited desktop connection and asks the original engine for its window inventory. An empty inventory means the connection worked but no windows were found; it does not prove accessibility or input works in every app.

Extract the next release bundle and rerun its installer to upgrade. It copies a separate release and atomically changes `current` only after validation. Corrupt bundles and failed validation leave the previous release selected. Old releases remain available. To roll back, select the intended directory under `releases` and atomically replace the `current` symlink; restart connected MCP clients afterward. No automatic runtime updates happen during agent use.

The installer checks the bundle architecture, SHA-256 file inventory, executable permissions, and symlink targets before modifying the installation. Missing payloads fail with a release-bundle error; source checkouts never fall back to a download.

## Build a release

Building requires Linux, Python 3.12+, `dpkg-deb`, CA certificates, and network access. Run on the target architecture, or in a matching Linux container:

```sh
python3 scripts/build_bundle.py --output dist
# Reuse an already downloaded, checksum-verified official package:
python3 scripts/build_bundle.py --output dist --package /absolute/chatgpt_arm64.deb
```

The build creates `lcu-0.2.0-linux-arm64.tar.gz` or `lcu-0.2.0-linux-x64.tar.gz`, plus a `.sha256` sidecar. It bundles the original runtime and all npm dependencies required for registration. Build/download utilities are excluded from the release archive. No OpenAI desktop-app package is needed on the target machine.

[runtime.lock.json](runtime.lock.json) pins the OpenAI version and esbuild downloads; agent installers have a separate npm lockfile. Unknown package hashes and unexpected source shapes fail closed. Generated archives belong in `dist/`; they contain the runtime but are not committed as source code.

## Runtime boundaries

Install and run LCU as the desktop account inside the intended VM or sandbox. LCU is not itself a sandbox: the standalone REPL runs with that account's permissions. Existing Codex sandbox and approval settings are preserved when supplied by the host. The original confirmation-policy handling remains in the runtime. LCU disables REPL analytics by default and never installs agent credentials.

The original compiled REPL and native engine are retained intact. JavaScript is specialized to Linux and bundled, with build input manifests recording the retained modules. Dedicated browser providers, other platform engines, and their instructions are excluded. Browser windows remain ordinary Linux windows.

The official Linux app preview does not yet advertise Computer Use as an enabled feature. LCU relies on a shipped implementation verified independently, not a supported standalone OpenAI SDK. [Official platform status](https://learn.chatgpt.com/docs/linux/linux-app#compatibility-and-limitations).

## Verify

The tests build a release, then install it and exercise independent GTK/Xlib applications in a separate Docker container with `--network none`. No personal desktop or agent account is accessed.

```sh
./tests/run.sh linux/arm64
./tests/run.sh linux/amd64
# Optional cached official package, still checksum-verified:
./tests/run.sh linux/arm64 /absolute/chatgpt_arm64.deb
```

See [verification results](docs/VERIFICATION.md) for exactly what passed and what remains untested.

## License

LCU's original packaging code and Luda-derived installation code are MIT licensed. The bundled OpenAI runtime and third-party dependencies retain their own terms and notices; LCU's MIT license does not relicense them. It is an independent project, not an OpenAI release.
