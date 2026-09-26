# LCU

**Codex computer use, decoupled from the Codex agent.**

LCU exposes Codex's original computer-use runtime to your harness. The official ChatGPT desktop app must still be installed locally: it supplies the runtime and instructions, while LCU handles setup and harness integration.

## Quick start

Copy this into your agent:

```text
Install and configure LCU for this harness using the latest release.
Follow https://raw.githubusercontent.com/0xpolarzero/lcu/main/docs/INSTALLATION.md
Check my OS, architecture, and prerequisites, then guide me through any required permissions.
```

Restart your harness after setup. Open a blank text-editor document and ask:

```text
Use LCU to inspect the open text editor, type “Hello from LCU”, and show me a screenshot.
```

Approve the app request and any operating-system prompts when they appear.

## Features

- **Desktop apps:** read windows, click, type, and take screenshots.
- **Chrome, when enabled:** read and control tabs through the official extension, with site approval.
- **In your harness:** adapters are currently available for Pi, Codex CLI, and Claude Code. Other harnesses can integrate through the [shared JavaScript client](docs/ADAPTERS.md#shared-client-contract).

## Requirements

Install [the official ChatGPT desktop app](https://chatgpt.com/download/), Python 3.12+, and your harness first. LCU checks the installed app for compatibility and uses its original runtime. For Codex CLI, [update before setup](docs/ADAPTERS.md#codex-cli) to get the required hook support.

| Platform | Requirements |
| --- | --- |
| Linux ARM64 or x86-64 | Ubuntu 24.04-compatible glibc system, an active X11 desktop, and D-Bus |
| macOS on Apple Silicon | The signed ChatGPT app, with Accessibility and screen-recording permissions approved during first use |

Windows 11 x64 remains a [candidate](docs/INSTALLATION.md#windows-11-x64-candidate-deferred-from-this-delivery). Intel Macs, native Wayland, and musl Linux are unsupported. See [verification and limits](docs/PARITY-STATUS.md) for tested behavior.

## Install manually

Download the archive and matching `.sha256` file from the [latest release](https://github.com/0xpolarzero/lcu/releases/latest):

| Platform | Archive |
| --- | --- |
| macOS on Apple Silicon | `lcu-<version>-darwin-arm64.tar.gz` |
| Linux ARM64 | `lcu-<version>-linux-arm64.tar.gz` |
| Linux x86-64 | `lcu-<version>-linux-x64.tar.gz` |

Follow the [installation guide](docs/INSTALLATION.md) to verify the checksum, extract the archive, and register LCU in your harness. Setup offers an agent chooser and desktop-readiness guidance. Chrome is opt-in.

For development, see [building from source](docs/DEVELOPMENT.md#building-from-source).

## Enable Chrome

Ask your agent:

```text
Enable Chrome control in my LCU setup using the installation guide:
https://raw.githubusercontent.com/0xpolarzero/lcu/main/docs/INSTALLATION.md#desktop-and-browser
```

Enable the official extension in your Chrome profile and restart your harness. Then ask it to use LCU to list Chrome tabs. Sites still require approval. Claude Code's Chrome support remains experimental because some interruptions do not trigger tab cleanup; see [adapter limitations](docs/ADAPTERS.md).

## Documentation

- [Installation](docs/INSTALLATION.md): downloads, harness setup, permissions, sessions, and upgrades.
- [Harness adapters](docs/ADAPTERS.md): custom clients, approvals, lifecycle, and result handling.
- [Verification](docs/PARITY-STATUS.md): tested behavior and remaining gaps.
- [Development](docs/DEVELOPMENT.md): source builds and isolated desktop tests.

LCU is [MIT licensed](LICENSE). Release archives contain LCU and third-party setup dependencies. The OpenAI app and its instructions come from your local installation and retain their own terms; see [dependency provenance](docs/PROVENANCE.md).
