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

### Packaged launch contract

The inspected `AppxManifest.xml` declares two applications: `App`, whose
entrypoint is `app/ChatGPT.exe`, and `CodexCoreCommandRunner`, whose entrypoint
is `app/resources/codex-command-runner.exe`. Its only app execution aliases are
`codex-chrome-native-host.exe` for the original Chrome extension host and
`codex-core-command-runner.exe` for that Core runner. It declares no alias or
application entrypoint for bundled `codex.exe`, `node.exe`, `node_repl.exe`, or
the CUA helper. Microsoft's [app execution alias documentation](https://learn.microsoft.com/en-us/windows/apps/desktop/modernize/desktop-to-uwp-extensions)
describes aliases as manifest-registered process entrypoints; its [MSIX runtime
documentation](https://learn.microsoft.com/en-us/windows/msix/desktop/desktop-to-uwp-behind-the-scenes)
describes the protected, read-only WindowsApps installation. The manifest does
not establish that all unaliased bundled executables are blocked; each launch
path needs its own native test.

The original Windows `@oai/sky` client, at
`app/resources/cua_node/bin/node_modules/@oai/sky/dist/project/cua/sky_js/src/targets/windows/internal/computer_use_client.js`,
resolves `bin/windows/codex-computer-use.exe` from its package. Its
`internal/helper_transport.js` directly spawns that helper with piped stdin,
stdout, and stderr and `windowsHide: true`. It does not invoke
`codex-core-command-runner.exe` in this path. The latter binary identifies
`--pipe-in`/`--pipe-out`, framed `SpawnRequest` fields, and registered package
image checks in its embedded strings. Those are evidence of an internal Codex
sandbox runner, not a documented general-purpose stdio entrypoint for LCU.
Reusing it as a CUA launcher would require an unproven private protocol and
would depart from the original Sky helper path. No such bridge was added.

In the disposable Windows 11 guest, the official MSIX deployed as
`OpenAI.Codex` `26.917.9434.0` x64 with Store signature. A direct invocation of
its installed `app/resources/codex.exe --version` from elevated PowerShell
returned `Access is denied`. This observation applies to that CLI invocation
only. Ordinary-user original Node, CUA helper, and LCU runtime results were
still pending when this source inspection was recorded.

The package's Chrome `installManifest.mjs` selects
`extension-host/windows/x64/extension-host.exe`, writes the host config under
the host's directory, writes a manifest under the current user's
`AppData/Local/OpenAI/extension` path constructed from `os.homedir()`, and registers that manifest under
`HKCU\\Software\\Google\\Chrome\\NativeMessagingHosts`. [Chromium's Windows
launcher](https://chromium.googlesource.com/chromium/src/+/main/chrome/browser/extensions/api/messaging/launch_context_win.cc)
starts `.exe` hosts directly and passes other manifest paths through `cmd.exe`.
That source supports a `.cmd` relay wrapper in principle. LCU's opt-in
Windows setup now runs the original installer, selects the original Windows
`extension-host.exe`, and redirects the generated manifest through a quiet
`.cmd` relay using the Python interpreter selected at installation. Its
binary-safe stdio and upstream browser authorization still need native
integration tests. Authorization must be shown to
work with the relay. This remains a browser parity blocker, not a reason to
bypass the original extension's approval policy.

`lcu/windows.py` reads the registered current-user package location through
`Get-AppxPackage`, checks exact identity/version/architecture, and hashes each
runtime component before returning original paths. Microsoft documents that
MSIX packages are [deployed per user into a protected, read-only package
location](https://learn.microsoft.com/en-us/windows/msix/desktop/desktop-to-uwp-behind-the-scenes).
The resolver neither extracts nor modifies the installed app. The Windows
branch in `lcu/runtime.py` selects the verified package paths and launches its
original Node/CUA entrypoint through `bin/lcu.cmd`. The thin Windows archive,
runtime-only installer, and account-local setup have fixture coverage. Those
tests do not prove native deployment, process launch, helper transport,
browser control, or GUI behavior.

A disposable Windows 11 Enterprise Evaluation VM is being installed on
`devbox` using the [official evaluation ISO](https://www.microsoft.com/en-us/evalcenter/download-windows-11-enterprise).
The official x64 ISO was 7,092,807,680 bytes with local SHA-256
`a61adeab895ef5a4db436e0a7011c92a2ff17bb0357f58b13bbc4062e535e7b9`.
It runs in an owned KVM container with 6 GiB RAM, four virtual CPUs, TPM,
UEFI, stock AHCI/e1000 devices, and a blank 80 GB sparse disk. The graphical
installer recognized the disk and reached its installation progress page
after the standard evaluation terms were accepted. No product key, Microsoft
account, or user credential was supplied. Python's [official 3.13.15 Windows
installer](https://www.python.org/downloads/release/python-31315/) was staged
for guest verification with its published SHA-256
`edec09c4853aeae9ac36efb8c9f95b68e2fee65eee56d9767a8b7c69c574403`.
Windows support remains open until the guest actually deploys the official
MSIX and proves the original CUA and optional Chrome flows end to end.
