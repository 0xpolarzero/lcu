# Installation

Install the current official ChatGPT desktop app for LCU's original computer-use runtime, then install the public agent CLIs you plan to use. LCU never downloads or installs these tools. If ChatGPT is missing, [download it](https://chatgpt.com/download/) and install it first. The current delivery supports an existing Ubuntu 24.04-compatible glibc desktop on ARM64 or x86-64 and Apple Silicon macOS. Linux requires an existing X11 desktop and D-Bus session owned by the target account; native Wayland and musl are unsupported. Python 3.12 or newer and the host's normal sandbox facilities are required. On macOS, LCU reuses the signed app in place; first-use permissions and an independent TextEdit save passed in a fresh guest ([verification](verification/macos-fresh-guest-2026-09-24.md)). The default installation enables native computer use only and does not install a Chrome native host or change a browser profile. LCU does not install a desktop, create a VM, or sign into ChatGPT.

## macOS and Pi

Install ChatGPT in `/Applications/ChatGPT.app` first, or install it elsewhere and pass that path with `--existing-app`. Then build the Darwin archive using [development instructions](DEVELOPMENT.md), extract it, install or update the standalone Codex CLI, and run as the intended desktop account:

~~~sh
npm install -g @openai/codex@latest
codex --version
./scripts/install.sh --existing-app /Applications/ChatGPT.app --agent codex
~~~

This reuses the selected signed app in place and installs LCU under `~/.local/share/lcu`. If the app is missing, setup stops with a download link; it never installs it. The app must retain the official bundle and signing identity, supported Apple Silicon architecture, valid runtime manifest, required files, and recognized original Codex CLI/code-mode-host components used by LCU's runtime integration. This internal app layout does not select the Codex CLI that runs agent turns: setup checks the public `codex` executable on the selected account's `PATH`. LCU reports the app and runtime versions it reads from that app; it does not require version or component-hash entries in the repository lock file. The check does not promise compatibility with arbitrary future APIs or layouts. Select another supported MCP agent with `--agent`, or use `--runtime-only` to defer agent setup. This command configures native computer use only.

Use the public standalone Codex CLI on the account's normal `PATH` for setup and interactive Codex sessions. If LCU reports that the CLI cannot load its `mcp_tool` lifecycle hooks, update it to the latest public release, then rerun setup. The 2026-09-27 contract run passed with standalone `codex-cli 0.157.1`; see [Codex CLI setup](ADAPTERS.md#codex-cli) and [the verification record](verification/codex-standalone-cli-2026-09-27.md).

~~~sh
npm install -g @openai/codex@latest
codex --version
~/.local/share/lcu/bin/lcu setup --agent codex
codex
~~~

Pi uses a native extension instead of requiring built-in MCP support. With Pi already installed, select it during LCU installation:

~~~sh
./scripts/install.sh --existing-app /Applications/ChatGPT.app --agent pi
pi
~~~

Setup installs the original local native skill and uses Pi's package installer to register the bundled extension. To add Pi to an existing LCU installation, run `lcu setup --agent pi`. Linux uses the same command. Add `--chrome` to setup only when you also want the original Chrome extension path configured for that account. The adapter selects the managed runtime; custom callers can still override it as described in [adapters](ADAPTERS.md). The [Pi approval regression](verification/pi-approval-2026-09-26.md) verifies that dismissing a browser-origin prompt cancels it and that an unrelated request is not accepted through an origin allowlist. Same-case text, PNG, WAV, and tool-error forwarding is tracked in the [adapter comparison](ADAPTERS.md#same-case-result-forwarding).

Interactive `lcu setup` runs a guided desktop-readiness check after agent registration. On macOS, the guide reads the selected app and signed helper names and paths, shows the relevant **Accessibility** and **Screen & System Audio Recording** (or **Screen Recording**) panes, and opens a pane only after you choose it. `lcu doctor` cannot read macOS privacy grants; it reports the original provider methods as available while keeping permission readiness unverified. The first verification is an approved call from the reconnected agent against a harmless window, such as a blank TextEdit document, asking LCU to return a screenshot.

`--yes` is unattended setup: it skips desktop readiness and prints the exact `lcu doctor` command to run later from the desktop account. `--check-desktop` performs a bounded noninteractive check, never opens System Settings, and exits nonzero when this platform cannot verify readiness. The original runtime remains responsible for its normal approval and macOS prompts.

Chrome mode also requires the official browser extension and site approval. For unattended use, a harness can pass exact origins the user already authorized via `LCU_APPROVED_ORIGINS`; this is an explicit grant, not a blanket bypass. The original provider chooses the platform instructions automatically.

## Windows 11 x64 candidate (deferred from this delivery)

Windows is deferred from the current LCU delivery. The candidate requires the official `OpenAI.Codex` Store app to already be installed and registered for the current Windows account; LCU does not download or install it. It targets Windows 11 x64 and validates the registered package identity, publisher, Store signature, architecture, and required host layout. Install Python 3.12 or newer, then extract the matching thin Windows ZIP and run from its extracted release directory in PowerShell:

~~~powershell
python .\scripts\install_windows.py --runtime-only
& "$env:LOCALAPPDATA\LCU\lcu.cmd" --version
~~~

To register a maintained agent instead, use `python .\scripts\install_windows.py --agent codex --yes`. The installer also accepts `claude-code` or `pi`; their installed-host prerequisites and lifecycle limits are in [harness adapters](ADAPTERS.md). Add `--chrome` only when the original external Chrome extension path is wanted. The default enables native computer use only. `--runtime-only` and `--agent` are alternative install modes.

The installer reads the selected package version and CUA runtime, inventories the complete registered package, and copies it unchanged into a private generation identified by that source-derived inventory. It records the observed metadata and validates the inventory when reusing the copy; it does not compare the app with a repository version or component-hash allowlist. Its source stays managed by Windows. The first private copy can take several minutes; the installer prints phase messages while it verifies and copies. LCU derives the original native host from the selected app under each thin release and switches the selected release after validation. It does not change WindowsApps permissions or system policy, require ChatGPT sign-in, or bundle the app in the thin ZIP. Reinstalling with the same prefix reuses a validated private app generation and retains prior releases.

The default-prefix private copy, runtime-only installer, `--version`, and `doctor` passed in a clean Windows 11 guest. The installed candidate also enumerated windows, captured a screenshot, and saved Unicode text to an existing Notepad file; an independent file read matched the expected bytes. A later installed candidate verified matching Stop/Interrupt cleanup, stale-turn isolation, and helper exit at MCP shutdown. Candidate f completed project-scoped native setup for Codex CLI, Claude Code, and Pi; the generated Windows skill and Pi files were verified. Its opt-in Chrome path passed a scripted original-MCP action through the official extension, including exact-origin approval and an independently verified save. No Windows real-model session or automatic Chrome per-turn cleanup test ran. The final Windows archive build and seal audit passed. See the [Windows guest record](verification/windows-source.md) for exact results.

## Linux: install LCU with an existing app

Install the official ChatGPT desktop app yourself before LCU. The default Linux app path is `/usr/lib/chatgpt`; if your installation is elsewhere, pass `--existing-app /absolute/path`. LCU copies the selected app into a private managed generation under its prefix and leaves the original installation in place. Extract an architecture-matching thin LCU archive, then install as root for automatic Ubuntu libraries:

~~~sh
sudo ./scripts/install.sh --user alice --runtime-only
~~~

Replace `alice` with the existing desktop account. This uses `/usr/lib/chatgpt` and installs the LCU runtime without registering an agent. To select an app installed at another path, add `--existing-app /absolute/path` to the install command. Install or update the public standalone Codex CLI for that account, then run setup and Codex as the desktop account, not root:

~~~sh
npm install -g @openai/codex@latest
codex --version
/opt/lcu/current/bin/lcu setup --agent codex
codex
~~~

The public Codex CLI `0.145.0` failed because its parser did not support `mcp_tool`; the current public `0.157.1` passed. Setup reports the selected executable, version, and parser error, then gives the official npm update command. See [Codex CLI setup](ADAPTERS.md#codex-cli). LCU no longer accepts `--app-package` as an app-acquisition route. If ChatGPT is not installed, download and install it yourself, then rerun LCU setup. For an existing app outside `/usr/lib/chatgpt`, use `--existing-app /absolute/path`. LCU validates the selected app and keeps a private managed copy; it does not replace or modify the original installation.

The default managed prefix is `/opt/lcu`. Use `--prefix /absolute/dedicated/path` for another location. A user-owned prefix needs system libraries preinstalled and `--skip-system`; `--offline` also requires `--skip-system`. Without `--skip-system`, apt installs LCU's Ubuntu system dependencies. This does not install ChatGPT: the existing app is copied into a private managed generation under the LCU prefix, and LCU leaves the source installation in place.

System library installation is a separate apt operation and cannot be rolled back as a single transaction with the LCU selection. Failed app validation or release selection leaves the previous current symlink in place. Existing running processes may still hold old generations; do not remove old app or LCU generations until they have exited.

The original package's AppArmor profile names /usr/lib/chatgpt/ChatGPT, its Electron UI. LCU directly launches the selected app's Node and CUA REPL, so that profile does not apply to LCU's native path and is not an LCU install requirement. The [ARM64 and x86-64 Ubuntu AppArmor tests](verification/installed-app-2026-09-23.md) passed native computer use and Chrome actions with AppArmor active; they recorded process labels and nonblocking `bwrap` denials. The x86-64 guest ran under KVM on physical AMD hardware. Keep the browser sandbox enabled; do not alter the system AppArmor policy to make a test pass.

## Account and agent registration

Use `--agent pi`, `codex`, or `claude-code` to select agents. Repeat `--agent` for several; `--agent all` selects all three, including agents not installed yet. `--agent auto` selects detected agents (their executable is on `PATH` or their usual config path exists). With no `--agent`, an interactive setup shows a chooser and marks detected agents, but waits for you to choose; it does not select them automatically. Noninteractive agent setup requires an explicit selection. Use `--runtime-only` to install LCU without registering an agent. The `claude` alias remains available. Install and authenticate each selected agent yourself; LCU does not install or authenticate agents. Setup uses the original installed CUA Node and a fixed third-party registration toolchain, then creates user-local byte-identical original instruction references. Pi receives its native extension; Codex CLI and Claude Code receive MCP registration. Setup preserves unrelated agent configuration values, although upstream registration tools can reformat files. Root setup drops to the selected account before writing account files. Other harnesses can use the shared client and portable export; additional integrations are open to contributions.

~~~sh
/opt/lcu/current/bin/lcu setup --agent codex --agent claude-code
./scripts/install.sh --list-agents
~~~

Unattended Linux registration skips desktop readiness. Use it only when setup cannot run interactively, then run `doctor` from the active desktop account's session:

~~~sh
/opt/lcu/current/bin/lcu setup --agent codex --yes
~~~

Later, from that account's active desktop session:

~~~sh
/opt/lcu/current/bin/lcu doctor
~~~

For project scope, use --scope project --project /absolute/project. Use --runtime-only to install without registration, then run /opt/lcu/current/bin/lcu setup --agent codex as the desktop account. --export /absolute/new/directory creates a portable LCU bootstrap and host contract, without OpenAI files or producer account paths. Its MCP command resolves /opt/lcu/current on the destination; set LCU_PREFIX for another installed prefix and LCU_SESSION_MODE=direct for an agent already inside the desktop session. On the destination machine, install LCU and a compatible official app and run setup --export again to generate original instruction references locally. Import that new export and the local full skill.

The original host contract advertises model-facing js and js_reset, keeps turn_ended for lifecycle and restricts module-directory injection. Generic MCP consumers must honor the exported visibility, output and lifecycle contract. MCP registration alone cannot enforce all agent-host behavior.

## Desktop and browser

The default --session discover mode attaches to exactly one existing XFCE session owned by the account. Other X11 desktops can use --session direct when the agent backend already has DISPLAY, DBUS_SESSION_BUS_ADDRESS and, when needed, XAUTHORITY. Use `--check-desktop` after setup to require a live, noninteractive readiness check. It never opens System Settings and exits nonzero when readiness is incomplete or unverifiable. You can also run:

~~~sh
/opt/lcu/current/bin/lcu doctor
~~~

Interactive setup launches the guided `lcu doctor` flow automatically after registration. `--yes` skips it; the command above can be run later from the active desktop account.

On macOS, `doctor` safely checks original runtime metadata and names the selected app/helper entries from their bundle metadata. It does not inspect application content or determine whether Accessibility or screen-capture grants are enabled. Its **Open** choices are explicit, and its recheck repeats only the metadata check. Readiness remains unverified until the connected agent makes its first approved screenshot call against a harmless window, such as a blank TextEdit document. A nonzero macOS doctor result means the grant state could not be verified through the original CLI API.

On Linux, `doctor` calls the original runtime's `list_windows` and `get_screenshot` methods. It reports only status and counts; LCU discards the returned image data locally. The original API may create its normal temporary capture files. A successful result verifies these two original runtime calls in the current desktop session, then asks you to verify an agent call.

On Windows, the existing original window-list check remains available. `doctor` reports that screenshot and Windows permission readiness are unverified; a window list alone is not a screenshot-readiness claim. Across platforms, generic provider errors remain runtime/backend failures unless the original API gives a specific supported error.

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
