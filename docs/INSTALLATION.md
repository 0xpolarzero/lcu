# Installation

LCU's verified Linux target is an existing Ubuntu 24.04-compatible glibc desktop on ARM64 or x86-64. The macOS Apple Silicon path reuses a signed local app; live TextEdit and opt-in Chrome actions passed, while cold helper startup and first-time OS permissions remain unverified. Linux requires an existing X11 desktop and D-Bus session owned by the target account; native Wayland and musl are unsupported. Python 3.12 or newer and the host's normal sandbox facilities are required. The default installation enables native computer use only and does not install a Chrome native host or change a browser profile. LCU does not install a desktop, create a VM, or sign into ChatGPT.

## macOS and Pi

Build the Darwin archive using [development instructions](DEVELOPMENT.md), extract it, and run as the intended desktop account:

~~~sh
./scripts/install.sh --existing-app /Applications/ChatGPT.app --agent codex --yes
~~~

This uses the pinned signed app 26.917.62051 in place and installs LCU under `~/.local/share/lcu`. Select another supported MCP agent with `--agent`, or use `--runtime-only` to defer agent setup. This command configures native computer use only. There is no macOS app downloader. An app update causes validation to reject it until reviewed version/hash pins are available. Apple Silicon is the only pinned macOS architecture.

Pi uses a native extension instead of requiring built-in MCP support. With Pi already installed, select it during LCU installation:

~~~sh
./scripts/install.sh --existing-app /Applications/ChatGPT.app --agent pi --yes
pi
~~~

Setup installs the original local native skill and uses Pi's package installer to register the bundled extension. To add Pi to an existing LCU installation, run `lcu setup --agent pi --yes`. Linux uses the same command. Add `--chrome` to setup only when you also want the original Chrome extension path configured for that account. The adapter selects the managed runtime; custom callers can still override it as described in [adapters](ADAPTERS.md). Pi's text/image results and empty-form approvals are supported; audio/resource results and nonempty approval forms remain explicit adapter limitations.

Explicit setup options with `--yes` suppress LCU's setup confirmation. They cannot grant macOS Screen Recording or Accessibility: those permissions belong to the original signed Codex Computer Use helper and may require approval in System Settings. Chrome mode also requires the official browser extension and site approval. For unattended use, a harness can pass exact origins the user already authorized via `LCU_APPROVED_ORIGINS`; this is an explicit grant, not a blanket bypass. The original provider chooses the platform instructions automatically.

## Windows 11 x64 candidate

Install the [pinned official `OpenAI.Codex` 26.917.9434.0 Store MSIX](https://persistent.oaistatic.com/codex-app-prod/releases/26.917.9434.0/ChatGPT-x64.msix) for the current Windows account, and install Python 3.12 or newer. Extract the matching thin Windows ZIP, then run from its extracted release directory in PowerShell:

~~~powershell
python .\scripts\install_windows.py --runtime-only
& "$env:LOCALAPPDATA\LCU\lcu.cmd" --version
~~~

To register a maintained agent instead, use `python .\scripts\install_windows.py --agent codex --yes`. The installer also accepts `claude-code` or `pi`; their installed-host prerequisites and lifecycle limits are in [harness adapters](ADAPTERS.md). Add `--chrome` only when the original external Chrome extension path is wanted. The default enables native computer use only. `--runtime-only` and `--agent` are alternative install modes.

The installer verifies the Store registration and pinned files, then copies the complete original package unchanged into `%LOCALAPPDATA%\LCU\apps\<package-hash>\app`. Its source stays managed by Windows. The first private copy can take several minutes; the installer prints phase messages while it verifies and copies. LCU derives the original native host under each thin release and switches the selected release after validation. It does not change WindowsApps permissions or system policy, require ChatGPT sign-in, or bundle the app in the thin ZIP. Reinstalling with the same prefix reuses a validated private app generation and retains prior releases.

The default-prefix private copy, runtime-only installer, `--version`, and `doctor` passed in a clean Windows 11 guest. The installed candidate also enumerated windows, captured a screenshot, and saved Unicode text to an existing Notepad file; an independent file read matched the expected bytes. Native-host lifecycle, agent registration, and opt-in Chrome are still being verified. See the [Windows guest record](verification/windows-source.md) for the exact result before treating this candidate as a supported Windows target.

## Linux: acquire and install

Extract an architecture-matching thin LCU archive. Install as root for automatic Ubuntu libraries:

~~~sh
sudo ./scripts/install.sh --user alice --agent codex --yes
~~~

For a local official package and no acquisition network:

~~~sh
sudo ./scripts/install.sh --user alice --agent codex --app-package /absolute/chatgpt.deb --offline --skip-system --yes
~~~

An exact compatible existing application can be supplied with --existing-app /absolute/usr/lib/chatgpt. Every file, link, and directory is compared with a verified architecture-matching official package before it is copied. The installer does not modify the source installation. A previously verified managed generation is reused on later LCU installs only when its complete inventory matches. An offline existing-app install needs a valid cached official package for this comparison. If the cache or installed generation is corrupt, setup fails closed and leaves the selected release unchanged.

The default managed prefix is /opt/lcu. Use --prefix /absolute/dedicated/path for another location. A user-owned prefix needs system libraries preinstalled and --skip-system. Strict --offline also requires --skip-system. A package download uses the fixed official URL and verifies its SHA-256 before extraction. The official package is not installed through apt: its post-install script would add an OpenAI apt source/key and load an AppArmor profile. LCU does not run that script. This is a private managed application installation, not a system package-manager installation.

System library installation is a separate apt operation and cannot be rolled back as a single transaction with the LCU selection. Failed app validation or release selection leaves the previous current symlink in place. Existing running processes may still hold old generations; do not remove old app or LCU generations until they have exited.

The original package's AppArmor profile names /usr/lib/chatgpt/ChatGPT, its Electron UI. LCU directly launches the selected app's Node and CUA REPL, so that profile does not apply to LCU's native path and is not an LCU install requirement. The [ARM64 and x86-64 Ubuntu AppArmor tests](verification/installed-app-2026-09-23.md) passed native computer use and Chrome actions with AppArmor active; they recorded process labels and nonblocking `bwrap` denials. The x86-64 guest ran under KVM on physical AMD hardware. Keep the browser sandbox enabled; do not alter the system AppArmor policy to make a test pass.

## Account and agent registration

Use --agent pi, codex, or claude-code. Repeat --agent for several, use all for these three agents, or auto for detected agents. The alias claude remains available. Install the selected agent separately; LCU does not install or authenticate it. Setup uses the original installed CUA Node and a fixed third-party registration toolchain, then creates user-local byte-identical original instruction references. Pi receives its native extension; Codex CLI and Claude Code receive MCP registration. Setup preserves unrelated agent configuration values, although upstream registration tools can reformat files. Root setup drops to the selected account before writing account files. Other harnesses can use the shared client and portable export; additional integrations are open to contributions.

~~~sh
sudo ./scripts/install.sh --user alice --agent codex --agent claude-code --yes
./scripts/install.sh --list-agents
~~~

For project scope, use --scope project --project /absolute/project. Use --runtime-only to install without registration, then run /opt/lcu/current/bin/lcu setup --agent codex --yes as the desktop account. --export /absolute/new/directory creates a portable LCU bootstrap and host contract, without OpenAI files or producer account paths. Its MCP command resolves /opt/lcu/current on the destination; set LCU_PREFIX for another installed prefix and LCU_SESSION_MODE=direct for an agent already inside the desktop session. On the destination machine, install LCU and its pinned app and run setup --export again to generate original instruction references locally. Import that new export and the local full skill.

The original host contract advertises model-facing js and js_reset, keeps turn_ended for lifecycle and restricts module-directory injection. Generic MCP consumers must honor the exported visibility, output and lifecycle contract. MCP registration alone cannot enforce all agent-host behavior.

## Desktop and browser

The default --session discover mode attaches to exactly one existing XFCE session owned by the account. Other X11 desktops can use --session direct when the agent backend already has DISPLAY, DBUS_SESSION_BUS_ADDRESS and, when needed, XAUTHORITY. Use --check-desktop to run a read-only window check after setup, or run:

~~~sh
/opt/lcu/current/bin/lcu doctor
~~~

For Chrome, explicitly opt in when registering the agent, then reconnect it. For example, as the desktop account run `lcu setup --agent codex --chrome --yes`. The selected browser and extension must run under that same account. To refresh the original native-host registration, run:

~~~sh
/opt/lcu/current/bin/lcu browser install
/opt/lcu/current/bin/lcu browser status
~~~

The official ChatGPT extension is how the original runtime reads and controls external Chrome tabs. It is required even when LCU runs without Codex sign-in. Desktop applications do not need it. Use your intended Chrome profile; a separate test profile is not an LCU requirement.

`browser install` invokes the original plugin's native-host installer from a user-local copy, then points the account's host manifest at LCU's relay. This command alone does not enable Chrome in an MCP process; direct clients must start `lcu --chrome`. It does not install or enable the Web Store extension. The relay locally enables the official extension's `x-browser-agent` label so Chrome actions do not require Codex sign-in. Sites can see that label; it is not a login credential. Enable the official extension in the intended Chrome profile using [OpenAI's extension setup instructions](https://learn.chatgpt.com/docs/chrome-extension). `browser status` uses the original diagnostics to report whether the extension is enabled and the connector points to this LCU installation; it changes nothing and does not claim a live connection. Complete the check by asking your agent to use LCU to list Chrome tabs.

[Google's Linux installation guide](https://support.google.com/chrome/answer/95346?hl=en) lists x86-64 and ARM64 Chrome packages. Chrome uses its user configuration for [native messaging host discovery](https://developer.chrome.com/docs/extensions/develop/concepts/native-messaging); a custom `--user-data-dir` profile must have access to the installed host manifest. Browser/extension compatibility with this pinned app remains a live test requirement. LCU does not select or change the default browser, browser profile, extension permissions, sign-in or site approvals. Do not use --browser-host, --with-browser-host, or lcu browser serve/protocol; they were IAB-only and now return migration errors.

The native-host manifest belongs to the Linux account, so other apps using this same extension and browser account also reach LCU's relay. The official extension stores the header-on decision in its Chrome profile after an agent session. Installing or removing the relay therefore does not automatically restore the original account-specific header decision in that profile.

Readiness is staged: package installed, desktop ready, extension discovered, then a browser action independently observed on a page under the intended no-sign-in policy. The installed ARM64 and x86-64 builds passed navigation, Unicode input, click, screenshot and tab close in disposable Ubuntu Chrome profiles; the local page observed `x-browser-agent` on browser requests. Site approval is still required. This local override does not reproduce a user-specific Codex feature-gate decision.

Custom harnesses must deliver the original instructions and images, present site approvals, and send completion/interruption events. The shared client and Pi reference adapter are documented in [adapters](ADAPTERS.md). Earlier OpenCode and Goose experiments remain in the [verification record](verification/installed-app-2026-09-23.md); neither is an advertised release integration.

## Upgrades and rollback

Reinstall with the same prefix. The installer keeps app generations under apps/, LCU generations under releases/, and atomically changes current only after validating the new release. Agent registrations point at current and should be reloaded after a switch. A failed setup can leave completed agent registrations even when another agent fails; its error lists which to retry. Old generations are retained so live processes do not lose their files.

The installer accepts the legacy positional prefix. --offline prohibits installation network calls and requires preinstalled system libraries with --skip-system; model and browser services can still need network during use. --yes confirms a selected noninteractive setup. See --help for the complete option list and [verification](VERIFICATION.md) for exact tested outcomes.
