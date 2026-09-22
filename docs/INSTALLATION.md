# Installation

Start with the [README](../README.md#install) to download and install a release. Run all commands on the Linux machine that hosts the desktop and agent backend.

## Requirements

- Linux ARM64 or x86-64 with glibc. Ubuntu 24.04 is tested; musl systems are unsupported.
- Python 3.12 or newer.
- An X11 desktop with a D-Bus session. Native Wayland is unsupported.
- A Linux account for the desktop and agent. The account and its home directory must already exist.

LCU supplies its own runtime and Node. The installer can install system libraries with apt. On another distribution, provide equivalent libraries and use `--skip-system`; those distributions have not been verified.

The required apt packages are `ca-certificates`, `python3`, `libx11-6`, `libxtst6`, `libxi6`, `libxrandr2`, `libxfixes3`, `libxcomposite1`, `libxdamage1`, `at-spi2-core`, `dbus-x11`, and `x11-utils`.

LCU does not install a desktop or agent. It does not start a login session or sign in to an agent service.

## Choose an account and agents

From an extracted release, install for the account that will run the agent:

```sh
sudo ./scripts/install.sh --user alice --agent codex --yes
```

Replace `alice` with an existing Linux account. Root must always provide `--user`. Other users can install only for their own account.

The installer registers both the MCP tools and the skill. Supported agent IDs are `codex`, `claude-code`, `cursor`, `gemini-cli`, `opencode`, `vscode`, and `copilot-cli`. `claude`, `gemini`, and `copilot` are aliases.

```sh
# Select two agents.
sudo ./scripts/install.sh --user alice --agent codex --agent claude-code --yes

# Select every supported agent, even if it is not installed yet.
sudo ./scripts/install.sh --user alice --agent all --yes

# Show supported agents without installing anything.
./scripts/install.sh --list-agents
```

Omit `--agent` and `--yes` to choose interactively. `--agent auto` selects detected agents. Automated installs need an explicit agent selection, `--export`, or `--runtime-only`.

Registration uses pinned versions of [skills](https://github.com/vercel-labs/skills) and [add-mcp](https://github.com/neon-solutions/add-mcp), included in the archive. They preserve unrelated configuration values, but can rewrite comments and formatting. Restart or reconnect your agent after setup so it loads the tools and skill.

## Connect to a desktop

By default, each launch connects to exactly one existing XFCE session owned by the account running LCU. It fails if no session or several sessions match.

For another X11 desktop, choose direct mode:

```sh
sudo ./scripts/install.sh --user alice --agent codex --session direct --yes
```

The agent backend must then run with the desktop's `DISPLAY`, `DBUS_SESSION_BUS_ADDRESS`, and any required `XAUTHORITY`. Direct mode uses that environment to connect. It does not discover or start a session.

Check the default XFCE connection as the desktop user:

```sh
/opt/lcu/current/bin/lcu-session --user "$(id -un)" -- /opt/lcu/current/bin/lcu doctor
```

For direct mode, run this from the same environment as the agent:

```sh
/opt/lcu/current/bin/lcu doctor
```

`doctor` lists windows. An empty list means the desktop connection worked but no windows were found. To check input and accessibility, ask your agent to inspect and interact with a test application.

**Using Codex's built-in SSH connection to a VM?** Install inside the VM for the SSH account. That is where the agent backend reads its configuration. An ordinary SSH command from a local agent does not load the remote machine's tools automatically.

## Custom install directory and offline use

The default directory is `/opt/lcu`. To install without root after system libraries are available:

```sh
./scripts/install.sh --prefix "$HOME/.local/share/lcu" --skip-system --agent codex --yes
```

The archive includes the runtime and agent-registration dependencies. With `--skip-system`, installation and registration work without network access. The agent's model service can still require a network connection.

The installer checks the archive's file inventory, architecture, permissions, and symlinks before installing. A source checkout has no runtime: use a release archive, or [build one](DEVELOPMENT.md).

## Add an agent later

Run setup as the desktop account:

```sh
/opt/lcu/current/bin/lcu setup --agent cursor --yes
```

To register in one project instead of the account's global configuration:

```sh
/opt/lcu/current/bin/lcu setup --agent cursor --scope project --project /absolute/project --yes
```

The project directory must exist. If you installed elsewhere, replace `/opt/lcu` with your prefix. Add `--session direct` when needed.

## Other agents

Agents that support stdio MCP and images can connect manually. For XFCE, run this command as the account named in `--user`:

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

For direct mode, set `command` to `/opt/lcu/current/bin/lcu` and `args` to `[]`. Supply the desktop environment described above.

Install [the skill](../skills/lcu/SKILL.md) in the location your agent uses for skills. You can also export the configuration and skill together:

```sh
/opt/lcu/current/bin/lcu setup --export /absolute/new/lcu-plugin --yes
```

The destination must not exist. The export contains `plugin.json`, `mcp.json`, and `skills/lcu/SKILL.md`. Import it if your client supports that format, or use the files separately. Choose either `--agent` or `--export`, not both. Custom clients have not all been tested; see [verification](VERIFICATION.md).

LCU exposes `js`, `js_reset`, `js_add_node_module_dir`, and `turn_ended`. Agents use `js` for the [desktop API](../instructions/api/tinysky-alt-core-cua-repl.md); the tool returns its instructions on first use.

## VM and container images

Provision the desktop, Python, system libraries, and user account first. Then install from the extracted archive:

```sh
./scripts/install.sh --user alice --agent all --skip-system --yes
```

The agents need not be installed yet. No running desktop or agent credentials are required during setup. Start the desktop before using the tools.

To install only the runtime, register agents later:

```sh
# During the image build, as root:
./scripts/install.sh --user alice --runtime-only --skip-system --yes

# Later, as alice:
/opt/lcu/current/bin/lcu setup --agent codex --yes
```

LCU runs with that account's permissions. Your VM or container provides isolation; LCU does not create a sandbox.

## Upgrade

Download the new release, verify its checksum, extract it, and run its installer with the same prefix and agent options.

The installer adds a versioned directory under `releases/` and switches `current` after validation. Failed validation leaves the previous release selected. Old releases stay available, and LCU does not update itself. Restart connected agents after upgrading.

To roll back, atomically replace the `current` symlink with one pointing to the previous directory under `releases/`, then restart connected agents.

### Migrate from Cual v0.1.0

Install LCU into the new default `/opt/lcu` directory and register your agents again. Remove each agent's old `cual` MCP entry and skill, then restart it. The old installation remains in place; LCU does not modify it.

## Installer options

Run `./scripts/install.sh --help` for the full interface. Common options:

| Option | Purpose |
| --- | --- |
| `--prefix PATH` | Choose the install directory. |
| `--user ACCOUNT` | Choose the existing desktop account. |
| `--agent NAME` | Select an agent; repeat to select several. Also accepts `all` or `auto`. |
| `--scope project --project PATH` | Register tools and skill in an existing project. |
| `--session discover` | Find the account's existing XFCE session; this is the default. |
| `--session direct` | Use the agent's desktop environment variables. |
| `--skip-system` | Skip apt; system libraries must already be present. |
| `--runtime-only` | Install without agent registration. |
| `--export PATH` | Export MCP configuration and skill to a new directory. |
| `--check-desktop` | Check the desktop connection after registration. |
| `--yes` | Apply the selected setup without a prompt. |

The installer also accepts a prefix as its first positional argument for compatibility with existing image scripts. Build-time `--package` and Luda's `--browser-config` are not installation options.
