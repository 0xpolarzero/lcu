# Windows x64 source and live guest verification (2026-09-24)

Windows is not a supported LCU target. The exact official package and thin LCU
archive installed in a disposable Windows 11 guest, but the original native
computer-use path failed before a screenshot or input action. The results below
separate installed-archive validation, original MCP transport, and native use.

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
`OpenAI.Codex` `26.917.9434.0` x64 with Store signature. Direct invocation of
its installed `app/resources/codex.exe --version` returned `Access is denied`
from elevated PowerShell. Direct invocation of its installed `node.exe --version`
returned the same error for the ordinary account. A successful read/hash and
an ordinary-account copy test below narrow those observations; neither error
alone identifies the Windows enforcement mechanism.

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
original Node/CUA entrypoint through `bin/lcu.cmd`. The thin archive and
runtime-only installer now have both fixture coverage and a live installation
check. Account-local agent registration, Chrome relay, and native control do
not have successful Windows guest tests.

### Live guest: installation and selected executable

The task-owned KVM guest ran [Microsoft's Windows 11 Enterprise Evaluation
ISO](https://www.microsoft.com/en-us/evalcenter/download-windows-11-enterprise),
7,092,807,680 bytes, SHA-256
`a61adeab895ef5a4db436e0a7011c92a2ff17bb0357f58b13bbc4062e535e7b9`.
It used 6 GiB RAM, four virtual CPUs, TPM, UEFI, AHCI/e1000 and an 80 GB sparse
disk. Standard OOBE completed with a generated guest-only local account and
unique synthetic VM identifiers. No Microsoft account, product key, ChatGPT
UI, or Codex login was used. The official [Python 3.13.15 installer](https://www.python.org/downloads/release/python-31315/)
had SHA-256 `edec09c4853aeae9ac36efb8c9f95b68e2fee65eee56d9767a8b7c69c574403`.

The first non-elevated `Add-AppxPackage` of the exact pinned MSIX failed with
`0x80073D28`: its packaged service required elevation. After ordinary guest
UAC approval, Windows registered `OpenAI.Codex` `26.917.9434.0` x64, publisher
`CN=50BDFD77-8903-4850-9FFE-6E8522F64D5B`, `SignatureKind: Store`. The
installed path was `C:\Program Files\WindowsApps\OpenAI.Codex_26.917.9434.0_x64__2p2nqsd0c76g0`.
Package installation did not launch the ChatGPT UI.

The experimental thin ZIP built from source `5a6aaf5` had SHA-256
`74015e33f7b42068fcce3cd7c25324ecf76d5eef37282302cd9d888a9899ec8a`.
The ordinary account extracted it and ran
`python -B scripts\install_windows.py --prefix %LOCALAPPDATA%\LCU --runtime-only`.
Archive seal verification, registered-app identity, all pinned component hashes,
and original CUA manifest validation passed. `%LOCALAPPDATA%\LCU\lcu.cmd
--version` printed `lcu 0.3.0 (ChatGPT windows 26.917.9434.0; CUA
0.0.16/20260915001755-492f19756c31)`. The actual installed `%LOCALAPPDATA%\LCU\lcu.cmd
doctor` then failed `LCU: [WinError 5] Access is denied` before native control.
The archive/installer pass is not a usable-runtime result.

As the ordinary account, `Get-FileHash` read the installed Node and Node REPL;
their hashes matched the lock. `Get-Acl` listed `BUILTIN\Users` with
`ReadAndExecute` on those files. A scoped query covering the denied launches
found no matching `node.exe`, `codex.exe`, or `OpenAI.Codex` event in
CodeIntegrity/Operational, AppLocker/EXE and DLL, or Windows Defender/Operational
over the preceding 30 minutes. These observations do not identify the denial
mechanism. A single ordinary-account copy of the installed `node.exe` to a
task-owned `LOCALAPPDATA` directory matched source SHA-256
`a604969e8eb5154a3d5617ff377c13b439e2436ff2ef98e546a05bd234724d78`
and printed `v24.21.0`, exit 0. This proves location-dependent launch behavior
for that one binary only.

### Live guest: intact original-runtime diagnostic

To test whether private reuse suffices without changing policy, an ordinary
account used `robocopy /E /COPY:DAT /DCOPY:DAT /R:1 /W:1` to copy the complete
registered `app` tree into a task-owned private directory. It did not copy
WindowsApps ACLs or modify the installed app. All 13 required original
component files matched the source SHA-256 pins after copying. LCU's existing
environment builder selected the private original `node.exe`, `node_repl.exe`,
`codex.exe`, module directory and original CUA launcher. It preserved the
original Node REPL sandbox and enabled only the native computer surface.

The original MCP process initialized at protocol `2024-11-05`, exposed `js`,
and executed pure JavaScript. Its first native `cua.listWindows({emit:false})`
failed `spawn EPERM` before listing a window. In the same original REPL kernel,
`child_process.spawnSync` of the same private Node executable with `--version`
also returned `EPERM`. Outside that kernel, the same private Node printed
`v24.21.0`, and the exact private Sky `codex-computer-use.exe` started and
rejected `--help` as an unknown argument (exit 1). This differential shows a
child-process restriction in the original Windows REPL context, including the
Sky helper spawn. It does not prove how Windows implements that restriction.

Source inspection shows the original ChatGPT app hosts a named-pipe transport
for its helper, while the inspected package exposes no standalone pipe-host
entry point. No synthetic pipe server, undocumented runner, sandbox disabling,
or package-permission change was used. A native screenshot, Notepad input/save,
independent file oracle, and opt-in Chrome action remain unproven. The Windows
build must stay experimental until an original, supported standalone native
transport passes those live checks. Guest screenshots and logs remain outside
Git and release archives. Local screenshots of the installed `--version`,
shipped `doctor` denial, one-file Node copy, scoped zero-match event query,
and full-copy `EPERM` comparison are `/private/tmp/lcu-win-sealfix-installed.png`,
`/private/tmp/lcu-win-installed-doctor-denied.png`,
`/private/tmp/lcu-win-node-copy-version.png`,
`/private/tmp/lcu-win-policy-events-zero.png`, and
`/private/tmp/lcu-win-full-copy-spawn-eperm.png` respectively. The source
scripts and complete raw logs remain in task-owned temporary storage and the
disposable guest; no host credential was copied into that evidence.
