# Installation

Start with the [README](../README.md#install) to build and install the current development archive; full standalone parity is still under verification. Run all commands on the Linux machine that hosts the desktop and agent backend.

## Requirements

- Linux ARM64 or x86-64 with glibc. Native-runtime tests use Ubuntu 24.04; provisioning for the newly bundled full application remains unvalidated. Musl systems are unsupported.
- Python 3.12 or newer.
- An X11 desktop with a D-Bus session. Native Wayland is unsupported.
- A Linux account for the desktop and agent. The account and its home directory must already exist.

LCU supplies its own Node, computer-use runtime, and complete original Owl application. Automatic apt provisioning targets Ubuntu 24.04 on both supported architectures. On another distribution, provide equivalent libraries and use `--skip-system`; those distributions have not been verified. The installer installs system dependencies separately, without installing the ChatGPT `.deb` or registering its desktop application.

The package list in [scripts/install.py](../scripts/install.py) covers every dependency declared by both pinned upstream packages, plus LCU's X11, session, audio, and sandbox prerequisites. The verification [Dockerfile](../tests/Dockerfile) contains the same runtime list and adds its desktop fixtures. It includes GTK/GLib and accessibility libraries; X11, DRM, GBM, OpenGL, and Mesa Vulkan drivers; NSS/NSPR and OpenSSL; ALSA/PulseAudio and FFmpeg; CUPS; USB/udev; TPM libraries; and the usual C/C++ runtime libraries. Apt resolves their transitive dependencies. The original dependency alternatives select `libglib2.0-bin` and `mesa-vulkan-drivers`.

Ubuntu 24.04 uses these names where the upstream control file uses older names:

| Upstream dependency name | Ubuntu 24.04 package |
| --- | --- |
| `libasound2`, `libcups2` | `libasound2t64`, `libcups2t64` |
| `libatk-bridge2.0-0`, `libatk1.0-0`, `libatspi2.0-0` | `libatk-bridge2.0-0t64`, `libatk1.0-0t64`, `libatspi2.0-0t64` |
| `libglib2.0-0`, `libgtk-3-0` | `libglib2.0-0t64`, `libgtk-3-0t64` |
| `libssl3` | `libssl3t64` |
| `libtss2-esys-3.0.2-0` | `libtss2-esys-3.0.2-0t64` |
| `libtss2-mu0` or `libtss2-mu-4.0.1-0t64` | `libtss2-mu-4.0.1-0t64` |
| `libtss2-tcti-device0` | `libtss2-tcti-device0t64` |

The UI/audio mappings come from the bundled Playwright 1.57.0 `lib/server/registry/nativeDeps.js` for `ubuntu24.04-x64`; its ARM64 entry uses the same lists. TPM and OpenSSL mappings are confirmed by Ubuntu's [ESYS](https://packages.ubuntu.com/noble/libtss2-esys-3.0.2-0t64), [MU](https://packages.ubuntu.com/noble/libtss2-mu-4.0.1-0t64), and [device transport](https://packages.ubuntu.com/noble/libtss2-tcti-device0t64) package records. See [provenance](PROVENANCE.md) for pinned source evidence.

These revised package lists have been checked against their sources but have **not yet passed a fresh apt installation or full Owl launch test**. Audio also requires a working Pulse-compatible monitor. Browser-provider requirements remain documented in [BROWSER-HOST-PARITY.md](BROWSER-HOST-PARITY.md).

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

On the first repeat of Codex setup, the original formatter expands the native
hook writer's inline arrays into TOML table arrays. Configuration values and
exact hook trust hashes stay unchanged; subsequent setup keeps the same bytes.

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

The archive includes the complete original application, its runtime and host executables/plugins, and agent-registration dependencies. With the required system libraries preinstalled, `--skip-system` requires no installation-time downloads. The agent's model service and the original browser authentication/policy services can still require network connections; offline installation does not imply all capabilities work offline.

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

Install [the complete skill directory](../skills/lcu/), including `references/`, in the location your agent uses for skills. You can also export the configuration and skill together:

```sh
/opt/lcu/current/bin/lcu setup --export /absolute/new/lcu-plugin --yes
```

The destination must not exist. The export contains `plugin.json`, `mcp.json`, `codex.mcp.json`, `host-contract.json`, and `skills/lcu/SKILL.md` with its complete `references/` directory. Import it if your client supports that format, or use the files separately. Choose either `--agent` or `--export`, not both. Custom clients have not all been tested; see [verification](VERIFICATION.md).

The raw original MCP server exposes `js`, `js_reset`, `js_add_node_module_dir`, and `turn_ended`. Codex host configuration filters module-directory injection and keeps `turn_ended` for lifecycle integration; the model sees `js` and `js_reset`. Other agent hosts must honor the exported tool/output contract and supply real turn completion signals. Agents use `js` for the [desktop API](../instructions/api/tinysky-alt-core-cua-repl.md); the tool returns its instructions on first use.

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
