# Installation

Install LCU from the [latest release](https://github.com/0xpolarzero/lcu/releases/latest), then register it in your harness. For source changes, see [Building from source](DEVELOPMENT.md#building-from-source).

## The `lcu` command

The installer does not add `lcu` to your `PATH`. Invoke it by its installed path:

| Platform | Installed command |
| --- | --- |
| macOS | `~/.local/share/lcu/current/bin/lcu` |
| Linux | `/opt/lcu/current/bin/lcu` (or `<prefix>/current/bin/lcu`) |
| Windows | `%LOCALAPPDATA%\LCU\lcu.cmd` |

Where a command below is written as `lcu ...`, run it through the installed path for your platform. This is the `mcp` server harnesses launch; running it directly in an interactive terminal only prints a hint that it is a stdio MCP server.

## If you are the installing agent

1. Check the OS, architecture, desktop account, and current harness. Adapters are `pi`, `codex`, `claude-code`, `omp` (Oh My Pi), and `hermes` (Hermes Agent); select the user's harness explicitly. OMP and Hermes are experimental; inspect their [verification limits](ADAPTERS.md) before claiming desktop behavior. If the harness has no adapter, report that gap and consult [the adapter contract](https://github.com/0xpolarzero/lcu/blob/main/docs/ADAPTERS.md). Do not substitute another harness.
2. Check the prerequisites below. The official desktop app, Python, and selected harness must already be installed. If anything is missing, report the prerequisite and its installation link; LCU does not install or authenticate them.
3. Download the matching archive and SHA-256 sidecar from the latest release, verify the checksum, and extract it. Follow the installation section for that platform from inside the extracted directory.
4. For unattended setup, add `--yes` to the command that selects the harness. Preserve the user's sandbox and approval settings. Enable Chrome or computer-audio recording only if the user requested it.
5. Report the installed path and tell the user to restart their harness and run the platform's `doctor` command from their desktop session. Installation and registration do not prove a desktop action worked; the user completes the first approved screenshot check.

## Prerequisites

- **An existing desktop:** Apple Silicon macOS, or Ubuntu 24.04-compatible glibc Linux on ARM64 or x86-64 with an X11 desktop and D-Bus session owned by the target account. Native Wayland and musl are unsupported; Windows is deferred.
- **The official ChatGPT desktop app:** [install it first](https://chatgpt.com/download/). Default paths are `/Applications/ChatGPT.app` on macOS and `/usr/lib/chatgpt` on Linux. Use `--existing-app /absolute/path` for another location. LCU never downloads or installs the app and does not require ChatGPT sign-in.
- **Python 3.12+** and the host's normal sandbox facilities.
- **Your installed, authenticated harness:** Pi, Codex CLI, Claude Code, Oh My Pi, or Hermes Agent. Codex CLI must support `mcp_tool` lifecycle hooks; update the public standalone CLI if setup reports a parser error. See [harness prerequisites](ADAPTERS.md).

LCU does not install a desktop or create a VM. Native computer use is the default; Chrome and computer-audio recording are opt-in.

## Download the release

Choose the archive for the machine where LCU will run:

| System | Archive suffix |
| --- | --- |
| Apple Silicon macOS | `darwin-arm64.tar.gz` |
| Linux ARM64 | `linux-arm64.tar.gz` |
| Linux x86-64 | `linux-x64.tar.gz` |

Download that archive and its matching `.sha256` file from the [latest release](https://github.com/0xpolarzero/lcu/releases/latest). Or run this from a terminal on the target machine; it selects the archive, checks its SHA-256, and opens the extracted directory:

~~~sh
case "$(uname -s)-$(uname -m)" in
  Darwin-arm64) LCU_TARGET=darwin-arm64 ;;
  Linux-aarch64|Linux-arm64) LCU_TARGET=linux-arm64 ;;
  Linux-x86_64) LCU_TARGET=linux-x64 ;;
  *) echo "Unsupported LCU platform" >&2; exit 1 ;;
esac
LCU_TAG=$(curl -fsSL https://api.github.com/repos/0xpolarzero/lcu/releases/latest |
  python3 -c 'import json, sys; print(json.load(sys.stdin)["tag_name"])')
LCU_ARCHIVE="lcu-${LCU_TAG#v}-${LCU_TARGET}.tar.gz"
LCU_URL="https://github.com/0xpolarzero/lcu/releases/download/$LCU_TAG"
mkdir -p lcu-release &&
cd lcu-release &&
curl -fLO "$LCU_URL/$LCU_ARCHIVE" &&
curl -fLO "$LCU_URL/$LCU_ARCHIVE.sha256" &&
if [ "$LCU_TARGET" = darwin-arm64 ]; then
  shasum -a 256 -c "$LCU_ARCHIVE.sha256"
else
  sha256sum -c "$LCU_ARCHIVE.sha256"
fi &&
  tar -xzf "$LCU_ARCHIVE" &&
  cd "${LCU_ARCHIVE%.tar.gz}"
~~~

Continue below only after the checksum reports **OK**. Use the extracted archive's installer; GitHub's automatic source-code downloads are not installable bundles.

## macOS

From the extracted release directory, run as the intended desktop account. Replace `codex` with `pi` or `claude-code` for your harness:

~~~sh
./scripts/install.sh --agent codex
~~~

Interactive installation registers the harness and guides you through desktop permissions. If an agent is running installation unattended, use `./scripts/install.sh --agent codex --yes`, then run this yourself from a desktop terminal:

~~~sh
~/.local/share/lcu/current/bin/lcu doctor
~~~

Restart your harness after setup. Ask it to use LCU to take a screenshot of a harmless window, such as a blank TextEdit document, and approve the request. This is the first check that macOS permissions allow an action.

LCU installs under `~/.local/share/lcu` and reuses the signed app and native helper in place. It validates the official identity/signature, Apple Silicon architecture, runtime manifest, required files, and recognized original host layout, then reports the observed app/runtime versions. It does not select apps through a repository version or component-hash allowlist. Compatibility still depends on the installed app retaining the host APIs and layout LCU uses. First-use permissions and an independent TextEdit save passed in a fresh guest ([verification](verification/macos-fresh-guest-2026-09-24.md)).

To add another harness later, run the installed command:

~~~sh
~/.local/share/lcu/current/bin/lcu setup --agent pi
~~~

Use the public standalone Codex CLI on the desktop account's normal `PATH`. If setup reports unsupported `mcp_tool` hooks, update it with `npm install -g @openai/codex@latest`, check `codex --version`, and rerun `~/.local/share/lcu/current/bin/lcu setup --agent codex`. See [Codex CLI setup](ADAPTERS.md#codex-cli) and [the verification record](verification/codex-standalone-cli-2026-09-27.md).

Pi setup uses Pi's package installer to register the bundled native extension and installs the original local skill. See [Pi approval verification](verification/pi-approval-2026-09-26.md) and [result forwarding](ADAPTERS.md#same-case-result-forwarding).

For Oh My Pi or Hermes Agent, install the harness first, then register its native integration:

```sh
~/.local/share/lcu/current/bin/lcu setup --agent omp
~/.local/share/lcu/current/bin/lcu setup --agent hermes
```

OMP setup calls `omp plugin link` on a generated local package containing the shared Pi extension and full local skill. Native links use the selected OMP user profile; project scope is rejected because OMP ignores it for local links. Hermes setup writes an LCU-owned plugin to `${HERMES_HOME:-~/.hermes}/plugins/lcu-cua`, includes the full local skill, and calls `hermes plugins enable lcu-cua`. Set an absolute `HERMES_HOME` to select another Hermes profile. Neither native integration supports project scope; setup rejects it. Restart the selected harness after registration. See [OMP](ADAPTERS.md#oh-my-pi) and [Hermes](ADAPTERS.md#hermes-agent) for behavior and evidence.

Interactive `lcu setup` runs a guided desktop-readiness check after agent registration. On macOS, the guide reads the selected app and signed helper names and paths, shows the relevant **Accessibility** and **Screen & System Audio Recording** (or **Screen Recording**) panes, and opens a pane only after you choose it. `lcu doctor` cannot read macOS privacy grants; it reports the original provider methods as available while keeping permission readiness unverified. The first verification is an approved call from the reconnected agent against a harmless window, such as a blank TextEdit document, asking LCU to return a screenshot.

`--yes` is unattended setup: it skips desktop readiness and prints the exact `lcu doctor` command to run later from the desktop account. `--check-desktop` performs a bounded noninteractive check, never opens System Settings, and exits nonzero when this platform cannot verify readiness. The original runtime remains responsible for its normal approval and macOS prompts.

Chrome mode also requires the official browser extension and site approval. For unattended use, a harness can pass exact origins the user already authorized via `LCU_APPROVED_ORIGINS`; this is an explicit grant, not a blanket bypass. The original provider chooses the platform instructions automatically.

## Linux

From the extracted release directory, run this in a terminal owned by the existing desktop account. It uses `/usr/lib/chatgpt`, installs Ubuntu system libraries, and installs the LCU runtime:

~~~sh
sudo ./scripts/install.sh --user "$(id -un)" --runtime-only
~~~

For an app installed elsewhere, add `--existing-app /absolute/path`. LCU leaves that installation in place and keeps a private managed copy under `/opt/lcu`.

Then, from a terminal inside the active X11 desktop session, register your harness as the desktop account, without `sudo`. Replace `codex` with `pi` or `claude-code`:

~~~sh
/opt/lcu/current/bin/lcu setup --agent codex --session direct
~~~

Interactive setup includes the desktop-readiness check. If an agent in that desktop session is running setup unattended, add `--yes`, then run this yourself from your desktop terminal:

~~~sh
/opt/lcu/current/bin/lcu doctor
~~~

Restart your harness from the desktop session and ask it to use LCU to take a screenshot of a harmless window. Approve the request and check the returned image. For an agent outside the desktop session, the default discovery mode can attach to an existing XFCE session; see [Desktop and browser](#desktop-and-browser).

If Codex setup reports unsupported `mcp_tool` hooks, update the public standalone CLI for that account with `npm install -g @openai/codex@latest`, check `codex --version`, and rerun setup. See [Codex CLI setup](ADAPTERS.md#codex-cli).

The default managed prefix is `/opt/lcu`. Use `--prefix /absolute/dedicated/path` for another location. A user-owned prefix needs system libraries preinstalled and `--skip-system`; `--offline` also requires `--skip-system`. Without `--skip-system`, apt installs LCU's Ubuntu system dependencies. This does not install ChatGPT: the existing app is copied into a private managed generation under the LCU prefix, and LCU leaves the source installation in place.

System library installation is a separate apt operation and cannot be rolled back as a single transaction with the LCU selection. Failed app validation or release selection leaves the previous current symlink in place. Existing running processes may still hold old generations; do not remove old app or LCU generations until they have exited.

The original package's AppArmor profile names /usr/lib/chatgpt/ChatGPT, its Electron UI. LCU directly launches the selected app's Node and CUA REPL, so that profile does not apply to LCU's native path and is not an LCU install requirement. The [ARM64 and x86-64 Ubuntu AppArmor tests](verification/installed-app-2026-09-23.md) passed native computer use and Chrome actions with AppArmor active; they recorded process labels and nonblocking `bwrap` denials. The x86-64 guest ran under KVM on physical AMD hardware. Keep the browser sandbox enabled; do not alter the system AppArmor policy to make a test pass.

## Account and agent registration

Use `--agent pi`, `codex`, `claude-code`, `omp`, or `hermes` to select agents. Repeat `--agent` for several; `--agent all` selects all five and reports missing harness prerequisites. OMP and Hermes restrict this combination to user scope. `--agent auto` selects detected agents (their executable is on `PATH` or their usual config path exists). With no `--agent`, an interactive setup shows a chooser and marks detected agents, but waits for you to choose. Noninteractive setup requires an explicit selection. Use `--runtime-only` to install LCU without registering an agent. Aliases are `claude`, `oh-my-pi`, and `hermes-agent`. Install and authenticate each selected harness yourself; LCU does neither. Setup runs the native harness registration tools with the release's private `agent-tools` Node runtime: on Linux this is a pinned Node 24.21 downloaded from nodejs.org into `agent-tools` when the archive is built; on macOS the build links the installed app's CUA Node. Setup then creates local byte-identical original instruction references. Pi receives an extension, OMP and Hermes receive native plugins, and Codex CLI and Claude Code receive MCP registration. Setup preserves unrelated configuration values, although upstream tools can reformat files. Root setup drops to the selected account before writing account files. Other harnesses can use the shared client and portable export.

~~~sh
/opt/lcu/current/bin/lcu setup --agent codex --agent claude-code
./scripts/install.sh --list-agents
~~~

Unattended Linux registration skips desktop readiness. Run it from a terminal inside the active X11 desktop session and keep `--session direct`, matching the main Linux flow; without it setup defaults to `--session discover`, which requires an existing XFCE session (see [Desktop and browser](#desktop-and-browser)). Then run `doctor` from that session:

~~~sh
/opt/lcu/current/bin/lcu setup --agent codex --yes --session direct
~~~

Later, from that account's active desktop session:

~~~sh
/opt/lcu/current/bin/lcu doctor
~~~

For project scope, use --scope project --project /absolute/project. Use --runtime-only to install without registration, then run /opt/lcu/current/bin/lcu setup --agent codex --session direct from inside the desktop session as the desktop account. --export /absolute/new/directory creates a portable LCU bootstrap and host contract, without OpenAI files or producer account paths. Its MCP command resolves /opt/lcu/current on the destination; set LCU_PREFIX for another installed prefix and LCU_SESSION_MODE=direct for an agent already inside the desktop session. On the destination machine, install LCU and a compatible official app and run setup --export again to generate original instruction references locally. Import that new export and the local full skill.

The original host contract advertises model-facing js and js_reset, keeps turn_ended for lifecycle and restricts module-directory injection. Generic MCP consumers must honor the exported visibility, output and lifecycle contract. MCP registration alone cannot enforce all agent-host behavior.

## Desktop and browser

On Linux, the default `--session discover` mode attaches to exactly one existing XFCE session owned by the account. Other X11 desktops use `--session direct` when the agent already has `DISPLAY`, `DBUS_SESSION_BUS_ADDRESS` and, when needed, `XAUTHORITY`. Run setup and the agent from a terminal in that desktop session. macOS uses direct mode automatically.

Pass `--check-desktop` to setup to require a noninteractive readiness check after registration. It never opens System Settings and exits nonzero when readiness is incomplete or unverifiable; agent registration remains saved. To repeat the interactive check, use the installed command (`~/.local/share/lcu/current/bin/lcu` on macOS). On Linux, run from the desktop session:

~~~sh
/opt/lcu/current/bin/lcu doctor
~~~

Interactive setup launches the guided `lcu doctor` flow automatically after registration. `--yes` skips it; the command above can be run later from the active desktop account.

On macOS, `doctor` safely checks original runtime metadata and names the selected app/helper entries from their bundle metadata. It does not inspect application content or determine whether Accessibility or screen-capture grants are enabled. Its **Open** choices are explicit, and its recheck repeats only the metadata check. Readiness remains unverified until the connected agent makes its first approved screenshot call against a harmless window, such as a blank TextEdit document. A nonzero macOS doctor result means the grant state could not be verified through the original CLI API.

On Linux, `doctor` calls the original runtime's `list_windows` and `get_screenshot` methods. It reports only status and counts; LCU discards the returned image data locally. The original API may create its normal temporary capture files. A successful result verifies these two original runtime calls in the current desktop session, then asks you to verify an agent call.

On Windows, the existing original window-list check remains available. `doctor` reports that screenshot and Windows permission readiness are unverified; a window list alone is not a screenshot-readiness claim. Across platforms, generic provider errors remain runtime/backend failures unless the original API gives a specific supported error.

For computer-audio recording, explicitly opt in when registering the agent, then reconnect it. For example, run `lcu setup --agent pi --audio`. This enables the original recording API and approval flow. LCU adds no audio-specific instructions, and saving audio to a file does not deliver it to the model. See [the audio opt-in verification record](verification/audio-opt-in-2026-09-27.md).

For Chrome, explicitly opt in when registering the agent, then reconnect it. For example, as the desktop account run `lcu setup --agent codex --chrome`. The selected browser and extension must run under that same account. To refresh the original native-host registration, run:

~~~sh
/opt/lcu/current/bin/lcu browser install
/opt/lcu/current/bin/lcu browser status
~~~

The official ChatGPT extension is how the original runtime reads and controls external Chrome tabs. It is required even when LCU runs without Codex sign-in. Desktop applications do not need it. Use your intended Chrome profile; a separate test profile is not an LCU requirement.

`browser install` invokes the original plugin's native-host installer from a user-local copy, then points the account's host manifest at LCU's relay. This command alone does not enable Chrome in an MCP process; direct clients must start `lcu --chrome`. It does not install or enable the Web Store extension. The relay locally enables the official extension's `x-browser-agent` label so Chrome actions do not require Codex sign-in. Sites can see that label; it is not a login credential. Enable the official extension in the intended Chrome profile using [OpenAI's extension setup instructions](https://learn.chatgpt.com/docs/chrome-extension). `browser status` uses the original diagnostics to report whether the extension is enabled and the connector points to this LCU installation; it changes nothing and does not claim a live connection. Complete the check by asking your agent to use LCU to list Chrome tabs.

[Google's Linux installation guide](https://support.google.com/chrome/answer/95346?hl=en) lists x86-64 and ARM64 Chrome packages. Chrome uses its user configuration for [native messaging host discovery](https://developer.chrome.com/docs/extensions/develop/concepts/native-messaging); a custom `--user-data-dir` profile must have access to the installed host manifest. Browser and extension compatibility with the selected app remains a live test requirement. LCU does not select or change the default browser, browser profile, extension permissions, sign-in or site approvals. Do not use --browser-host, --with-browser-host, or lcu browser serve/protocol; they were IAB-only and now return migration errors.

The native-host manifest belongs to the Linux account, so other apps using this same extension and browser account also reach LCU's relay. The official extension stores the header-on decision in its Chrome profile after an agent session. Installing or removing the relay therefore does not automatically restore the original account-specific header decision in that profile.

Readiness is staged: package installed, desktop ready, extension discovered, then a browser action independently observed on a page under the intended no-sign-in policy. The installed ARM64 and x86-64 builds passed navigation, Unicode input, click, screenshot and tab close in disposable Ubuntu Chrome profiles; the local page observed `x-browser-agent` on browser requests. Site approval is still required. This local override does not reproduce a user-specific Codex feature-gate decision.

Custom harnesses must deliver the original instructions and images, present site approvals, and send completion/interruption events. The shared client and Pi reference adapter are documented in [adapters](ADAPTERS.md). Earlier OpenCode and Goose experiments remain in the [verification record](verification/installed-app-2026-09-23.md); neither is an advertised release integration.

## Upgrades and rollback

Reinstall with the same prefix. The installer keeps app generations under apps/, LCU generations under releases/, and atomically changes current only after validating the new release. Agent registrations point at current and should be reloaded after a switch. A failed setup can leave completed agent registrations even when another agent fails; its error lists which to retry. Old generations are retained so live processes do not lose their files.

The installer accepts the legacy positional prefix. --offline prohibits installation network calls and requires preinstalled system libraries with --skip-system; model and browser services can still need network during use. --yes confirms a selected noninteractive setup. See --help for the complete option list and [verification](VERIFICATION.md) for exact tested outcomes.

## Windows 11 x64 candidate (deferred from this delivery)

Windows is deferred from the current LCU delivery. The candidate requires the official `OpenAI.Codex` Store app to already be installed and registered for the current Windows account; LCU does not download or install it. It targets Windows 11 x64 and validates the registered package identity, publisher, Store signature, architecture, and required host layout. Install Python 3.12 or newer, then extract the matching thin Windows ZIP and run from its extracted release directory in PowerShell:

~~~powershell
python .\scripts\install_windows.py --runtime-only
& "$env:LOCALAPPDATA\LCU\lcu.cmd" --version
~~~

To register an agent instead, use `python .\scripts\install_windows.py --agent codex --yes`. The installer accepts the common harness IDs; their installed-host prerequisites and lifecycle limits are in [harness adapters](ADAPTERS.md). OMP and Hermes remain experimental and have no Windows host verification; OMP also requires its generated package and LCU release on the same drive. Add `--chrome` only when the original external Chrome extension path is wanted. The default enables native computer use only. `--runtime-only` and `--agent` are alternative install modes.

The installer reads the selected package version and CUA runtime, inventories the complete registered package, and copies it unchanged into a private generation identified by that source-derived inventory. It records the observed metadata and validates the inventory when reusing the copy; it does not compare the app with a repository version or component-hash allowlist. Its source stays managed by Windows. The first private copy can take several minutes; the installer prints phase messages while it verifies and copies. LCU derives the original native host from the selected app under each thin release and switches the selected release after validation. It does not change WindowsApps permissions or system policy, require ChatGPT sign-in, or bundle the app in the thin ZIP. Reinstalling with the same prefix reuses a validated private app generation and retains prior releases.

The default-prefix private copy, runtime-only installer, `--version`, and `doctor` passed in a clean Windows 11 guest. The installed candidate also enumerated windows, captured a screenshot, and saved Unicode text to an existing Notepad file; an independent file read matched the expected bytes. A later installed candidate verified matching Stop/Interrupt cleanup, stale-turn isolation, and helper exit at MCP shutdown. Candidate f completed project-scoped native setup for Codex CLI, Claude Code, and Pi; the generated Windows skill and Pi files were verified. Its opt-in Chrome path passed a scripted original-MCP action through the official extension, including exact-origin approval and an independently verified save. No Windows real-model session or automatic Chrome per-turn cleanup test ran. The final Windows archive build and seal audit passed. See the [Windows guest record](verification/windows-source.md) for exact results.
