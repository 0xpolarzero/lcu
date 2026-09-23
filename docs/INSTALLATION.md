# Installation

LCU runs on an existing Ubuntu 24.04-compatible glibc Linux desktop. Supported CPU architectures are ARM64 and x86-64. The target account must exist and own an X11 desktop with D-Bus. Native Wayland and musl are unsupported. Python 3.12 or newer and the host's normal sandbox facilities are required. LCU does not install a desktop, create a VM, sign into ChatGPT, or change the browser's default profile.

## Acquire and install

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

Use --agent codex, claude-code, cursor, gemini-cli, opencode, vscode, or copilot-cli. Repeat --agent for several, use all for every supported agent, or auto for detected agents. Aliases claude, gemini and copilot remain available. Setup uses the original installed CUA Node and a fixed third-party registration toolchain, then creates user-local byte-identical original instruction references before it registers MCP. It preserves unrelated agent configuration values, although upstream registration tools can reformat files. Root setup drops to the selected account before writing account files.

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

For Chrome, the selected browser and extension must run under the same Linux account as LCU. Agent setup installs the original native host for that account. To refresh it, run:

~~~sh
/opt/lcu/current/bin/lcu browser install
~~~

This invokes the original plugin's native-host installer from a user-local copy, then points the account's host manifest at LCU's relay. The relay locally enables the official extension's `x-browser-agent` label so Chrome actions do not require Codex sign-in. Sites can see that label; it is not a login credential. Then enable the official extension in the intended Chrome profile using [OpenAI's extension setup instructions](https://learn.chatgpt.com/docs/chrome-extension). [Google's Linux installation guide](https://support.google.com/chrome/answer/95346?hl=en) lists x86-64 and ARM64 Chrome packages. Chrome uses its user configuration for [native messaging host discovery](https://developer.chrome.com/docs/extensions/develop/concepts/native-messaging); a custom `--user-data-dir` profile must have access to the installed host manifest. Browser/extension compatibility with this pinned app remains a live test requirement. LCU does not select or change the default browser, browser profile, extension permissions, sign-in or site approvals. Do not use --browser-host, --with-browser-host, or lcu browser serve/protocol; they were IAB-only and now return migration errors.

The native-host manifest belongs to the Linux account, so other apps using this same extension and browser account also reach LCU's relay. The official extension stores the header-on decision in its Chrome profile after an agent session. Installing or removing the relay therefore does not automatically restore the original account-specific header decision in that profile.

Readiness is staged: package installed, desktop ready, extension discovered, then a browser action independently observed on a page under the intended no-sign-in policy. The installed ARM64 and x86-64 builds passed navigation, Unicode input, click, screenshot and tab close in disposable Ubuntu Chrome profiles; the local page observed `x-browser-agent` on browser requests. Site approval is still required. This local override does not reproduce a user-specific Codex feature-gate decision.

The agent host must support MCP site-approval elicitation for Chrome actions. OpenCode 1.18.32 delivered LCU's tools and instructions but did not advertise elicitation, so the pinned browser provider blocked its page request. Goose 1.51.0 did not initialize the pinned MCP server because it sent `server/discover` first. Registration success alone does not establish browser-action readiness in either product; see the [verification record](verification/installed-app-2026-09-23.md).

## Upgrades and rollback

Reinstall with the same prefix. The installer keeps app generations under apps/, LCU generations under releases/, and atomically changes current only after validating the new release. Agent registrations point at current and should be reloaded after a switch. A failed setup can leave completed agent registrations even when another agent fails; its error lists which to retry. Old generations are retained so live processes do not lose their files.

The installer accepts the legacy positional prefix. --offline prohibits installation network calls and requires preinstalled system libraries with --skip-system; model and browser services can still need network during use. --yes confirms a selected noninteractive setup. See --help for the complete option list and [verification](VERIFICATION.md) for exact tested outcomes.
