# Windows x64 source inspection (2026-09-24)

Windows is not yet a supported LCU target. This records an inspected official
package and a fixture-tested selection seam; it is not Windows desktop proof.

The [official OpenAI Windows update manifest](https://persistent.oaistatic.com/codex-app-prod/windows-store-update.json)
identified `OpenAI.Codex` build `26.917.9434.0`. Its
`https://persistent.oaistatic.com/codex-app-prod/releases/26.917.9434.0/ChatGPT-x64.msix`
response was an 830,521,537-byte MSIX. The downloaded package's SHA-256 was
`9892383820c5505997456bde8385810afadd6076ae7fff9e3835a48ca0555c98`.
No MSIX payload was added to Git. The package contains `AppxSignature.p7x`;
this macOS inspection did not verify the signature as Windows does during
deployment. The pin source and component hashes are in `runtime.lock.json`.

`AppxManifest.xml` identifies `OpenAI.Codex`, `x64`, version `26.917.9434.0`,
publisher `CN=50BDFD77-8903-4850-9FFE-6E8522F64D5B`, and
`Windows.Desktop` minimum `10.0.19041.0`. It registers the original
`extension-host.exe` as the `codex-chrome-native-host.exe` execution alias and
excludes the current-user Chrome native-messaging registry key from
virtualization. The package includes the original Node `24.21.0`,
`node_repl.exe`, CUA launcher, `codex.exe`, `codex-code-mode-host.exe`,
`@oai/sky` Windows helper and Swift backend, Chrome native host, plugins,
and original instructions. Its CUA manifest names platform `windows`,
architecture `x64`, runtime `0.0.16/20260915001755-492f19756c31`.

The package's Chrome `installManifest.mjs` selects
`extension-host/windows/x64/extension-host.exe`, writes the host config under
the host's directory, writes a manifest under
`%LOCALAPPDATA%/OpenAI/extension`, and registers that manifest under
`HKCU\\Software\\Google\\Chrome\\NativeMessagingHosts`. [Chromium's Windows
launcher](https://chromium.googlesource.com/chromium/src/+/main/chrome/browser/extensions/api/messaging/launch_context_win.cc)
starts `.exe` hosts directly and passes other manifest paths through `cmd.exe`.
That source supports a `.cmd` relay wrapper in principle. The current POSIX
`lcu/native_host.py` shebang alone cannot serve as a Windows host; a quiet
`.cmd` wrapper, binary-safe stdio, and the original Windows `extension-host.exe`
need native integration tests. Upstream browser authorization must be shown to
work with the relay. This remains a browser parity blocker, not a reason to
bypass the original extension's approval policy.

`lcu/windows.py` reads the registered current-user package location through
`Get-AppxPackage`, checks exact identity/version/architecture, and hashes each
runtime component before returning original paths. Microsoft documents that
MSIX packages are [deployed per user into a protected, read-only package
location](https://learn.microsoft.com/en-us/windows/msix/desktop/desktop-to-uwp-behind-the-scenes).
The resolver neither extracts nor modifies the installed app. The Windows
branch in `lcu/runtime.py` selects the verified package paths and launches its
original Node/CUA entrypoint through `bin/lcu.cmd`. Ten disposable fixture
tests passed across `tests.test_windows_package` and
`tests.test_windows_runtime`; they do not prove native deployment, process
launch, helper transport, browser control, or GUI behavior. Windows `lcu setup`
and `lcu browser install` explicitly report that those paths are not yet
implemented.

No disposable Windows session was available locally or on `devbox` at
inspection time. `devbox` has Docker, `/dev/kvm`, 13 GiB available memory,
117 GiB free disk, and no existing containers. A minimal 6 GiB RAM, 50 GiB
sparse-disk VM is technically feasible on that host. The [consumer Windows 11
ISO page](https://www.microsoft.com/en-us/software-download/windows11) offers
a VM ISO but describes a product-key-dependent edition. Microsoft says setup
includes [EULA acceptance](https://learn.microsoft.com/en-us/windows-hardware/customize/desktop/customize-oobe-in-windows-11).
No Windows installation, account sign-in, license acceptance, or GUI test was
performed. Windows support remains open until a properly licensed disposable
Windows 11 x64 VM can install the official MSIX and run the original CUA and
browser flows end to end.
