# macOS test guest recovery and acceptance status, 2026-09-28

The disposable UTM guest `LCU macOS cold helper test`, UUID
`34461462-A64A-4740-9A68-458E1748EB15`, was recovered and logged in to the
normal desktop as `lcuverify`. It is now stopped after the final
acceptance diagnostic exceeded its time budget. It uses Apple Virtualization
model `VirtualMac2,1`, macOS 26.6.2, and arm64. The task-owned original
Computer Use runtime managed only this guest.

The original `lcutest` account and data remain intact. Its offline password
reset stopped when Apple's `dscl -passwd` interface requested the old password;
the blank response returned `eDSAuthFailed`. Apple's Recovery `resetpassword`
deactivation separately returned “Failed to deactivate device.” Neither path
was repeated, and no disk data was erased or manually edited. A separate local
administrator `lcuverify` (UID 502, primary group 20) was created through the
documented offline `dscl -f … localonly` interface and successfully logged in.
Its fixture credential is stored only at
`.verification/private/utm-lcuverify-password.txt` (ignored by Git; file mode
0600 under a mode-0700 directory). This locator is private test state, not a
password value. Apple Account sign-in was skipped, analytics stayed disabled,
Siri was disabled, and FileVault remained unchanged.

The guest reuses its existing `/Applications/ChatGPT.app` in place: bundle
`com.openai.codex`, observed version `26.917.62051`, build `10789`, signature
identifier `com.openai.codex`, team `2DC432GLL2`, with successful `codesign`
verification. The observed CUA runtime is `0.0.16`. No app or native helper
was copied, modified, or re-signed. Guest inventory is recorded at
`/private/tmp/lcu-macos-audio-acceptance-20260927/http-results/inventory.json`.
The guest fetched task-only source/build inputs and test scripts over the
UTM host-only HTTP endpoint `192.168.64.1:1080`; it did not fetch the official
app or helper. Results used fixed `/result/...` endpoints.

The original audio baseline and LCU audio path passed on the current-source
archive with SHA-256
`0b57b8c3b8e7b2557d6e15219e22883cf0903a524bc463cecb6539daf274f9bb`:
a generated 440 Hz tone was measured at 440.1 Hz through the original API and
434.9 Hz through LCU, and both returned audio streams matched their recorded
bytes. No provider request occurred. Earlier stale-archive audio evidence is
not used as evidence for current behavior.

An earlier source-frozen archive used for Stop diagnostics has SHA-256
`7cc10bf29ab5012231ff0fc6aaa4b6fed952427ac4ced97cc8d2c186d17659af` and was
installed offline at `/Users/lcuverify/lcu-installed/current`. This historical
diagnostic accepted AppStop between native calls but its fresh-turn TextEdit
action still returned the stopped-session response, so that archive's recovery
oracle failed. It is not the latest acceptance result.

The current-source archive used for final Stop acceptance has SHA-256
`10021a5f83f26c70a99493d412aad6312b630e9b0626558164c3c30e58e12b6e`.
The bounded between-call run passed: AppStop was accepted for
`com.apple.TextEdit`, the next action returned the original
stopped-for-this-turn response, and a fresh turn completed its TextEdit
save/file oracle with the matching session ID, a new turn ID, and a matching
MCP `call_id`. No approval was persisted and no provider/model request occurred.
This run explicitly skipped stopping an in-flight native MCP request, so it
does not establish pending-call Stop behavior.

A separate bounded pending-call run on that archive exceeded its time budget
while the generated TextEdit input continued. After the timeout, the guest
was left without further test input; no valid pending-call result was
produced. Do not treat that run as a pass or failure of the native Stop
outcome. The diagnostic shell was fetched but not executed. UTM's graceful
guest shutdown request did not stop the VM, so the disposable VM was powered
off with `utmctl stop --force`; its disk and both accounts were preserved.

The earlier bounded recovery metadata diagnostic on the historical `7cc10bf`
archive confirmed the original
`turn_ended` schema (`hook_event_name`, `session_id`, `turn_id`), successful
turn cleanup, matching fresh session metadata, a new recovery turn ID, and a
matching MCP call ID. Those checks did not restore native actions after Stop
in that historical run; the current-source V2 result above proves recovery.
Read-only guest binary audits recorded hashes and marker checks without
copying app files or source. The later `nm`/`otool` audit was inconclusive:
`xcode-select -p` returned code 2, and the available developer tools failed on
the binaries. No TCC reset or database edit was made. The guest remains
recovered; the VM is stopped with its disk, login account, and private fixture
credential preserved.

The passing between-call result is preserved separately from the later
pending-call attempt. Stop and audit results are under
`/private/tmp/lcu-macos-audio-acceptance-20260927/http-results/`; these files
are task-local temporary evidence. The fixture credential remains private and
is not included in this document.
