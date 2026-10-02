# Harness adapters

LCU keeps the selected installed app's original CUA MCP server authoritative for instructions, execution, elicitation, policy, and lifecycle. It does not implement browser control, screenshots, accessibility, input, or JavaScript execution. The Pi client, Claude relay, and Codex relay use the official MCP SDK. The Codex relay passes original initialization instructions and public `js`/`js_reset` descriptors through, but intentionally omits `js_add_node_module_dir` and `turn_ended` from model-visible `tools/list`. It still forwards host calls to those original tools; the installed Codex Stop hook reaches `turn_ended` with the original session and turn IDs. This is an explicit visibility adaptation, not full `tools/list` parity.

## Shared client contract

```js
import { createCuaClient } from './adapters/client.mjs';

const cua = createCuaClient({
  command: ['/absolute/path/to/lcu'],
  onElicitation: async params => {
    // Render the original request. This placeholder cancels it.
    return { action: 'cancel' };
  },
});
await cua.connect();
const instructions = cua.instructions; // original MCP initialization instructions
const tools = cua.publicTools();       // original js and js_reset descriptors
const result = await cua.call('js', { code: 'await cua.getState()' }, { sessionId, turnId });
// Forward result.content and result.isError unchanged to the model.
await cua.turnEnded({ sessionId, turnId, event: 'Stop' });
await cua.close();
```

Before the first CUA call, the host must put the original initialization instructions and public tool descriptors into model context, as official Codex does. LCU registers no skill. Forward original result content and error state unchanged. Keep one connection alive through the turn and use real host session/turn IDs. `turn_ended`, `js_add_node_module_dir`, and Claude's `set_turn_context` are host-only tools; do not expose them to the model. Invoke original cleanup only for lifecycle events the host reports. The shared client cancels unresolved elicitation when `onElicitation` is absent. Otherwise, render the original request and return the user's actual response. `allowedOrigins` is only for exact HTTP(S) origins the user explicitly approved. LCU keeps no permission cache.

## Linux sandbox state

The original `node_repl` reads `_meta["codex/sandbox-state-meta"]` (a `permissionProfile` and a `sandboxCwd` file URI) on every tool call. Without it, on a machine where bubblewrap works, it wraps both the JavaScript kernel and the trusted Sky worker in `codex sandbox` with a read-only filesystem and no network. The seccomp filter that implements "no network" also refuses connecting to the X11 Unix socket, so every Linux computer-use call fails. Only a `disabled` profile removes the wrapper; the network field of a `managed` or `external` profile has no effect (observed with the Codex CLI the app ships: `network = {enabled = false}` in every sandboxed command line).

What each host sends: Codex CLI sends the metadata only to servers that advertise the `codex/sandbox-state-meta` capability, and the Codex relay does not advertise it, so it sends nothing; Claude Code, Pi, Oh My Pi, the Hermes bridge and generic MCP clients never send it. LCU therefore supplies the default itself: `lcu` adds `{"permissionProfile": {"type": "disabled"}, "sandboxCwd": "<launch directory as a file URI>"}` to `NODE_REPL_REQUEST_META` on Linux, next to the connection identity it already adds. This is the same state official Codex sends under `danger-full-access`. Original approvals still gate computer use; the removed layer only confined the model's JavaScript on a path that cannot work confined.

Precedence is unchanged: per-call `_meta` overrides the default, and a `NODE_REPL_REQUEST_META` that already contains `codex/sandbox-state-meta` is left untouched, so a host that deliberately sends a stricter profile still gets it (and will see the X11 error). A host that registers bare `lcu` with Codex CLI directly would make Codex send its real turn profile; use the generated relay registration or `danger-full-access` for computer use. `LCU_NODE_REPL_SANDBOX=host` disables the default. Other platforms are unchanged.

**Security consequence.** With the default, the original `node_repl` JavaScript kernel (the code the model writes in `js` calls) runs without the sandbox: it can write files outside the workspace, use the network and start subprocesses as the account running the harness. Original approvals still gate computer use itself, but they do not confine that JavaScript. **Why LCU accepts this:** the current Linux runtime's network-off seccomp filter also blocks the X11 socket, so no sandboxed profile can reach the desktop; macOS uses a signed native helper over an allowed pipe, so it is unaffected. The Codex relay does not forward Codex's own sandbox mode today, so `read-only` or `workspace-write` in Codex does not restrict the kernel. This will be revisited when OpenAI's runtime gains an X11 socket exception.

**Opting out.** `LCU_NODE_REPL_SANDBOX=host` must be in the environment of the `lcu` process. Codex filters the MCP child's environment and LCU registers no `env_vars`, so `LCU_NODE_REPL_SANDBOX=host codex` never reaches LCU; set it under `[mcp_servers.lcu.env]` instead. The per-harness locations are in the [installation guide](INSTALLATION.md#linux-sandbox-and-input-notes), and `tests/codex_mcp_env.py` reproduces the filtering with an isolated Codex CLI. Pi, Oh My Pi and the Hermes bridge start `lcu` with their own process environment, so exporting the variable before launching them works.

`tests/adapter_paths.py` runs the GTK oracle flow through a bare client, the Codex relay, the Claude relay, the shared client used by Pi and Oh My Pi, and the Hermes bridge with no sandbox metadata; `tests/run.sh` runs it in a container where the sandbox is active and checks the negative control and a stricter host profile.

## Linux window-targeted input

The original Linux engine (`sky_linux`) delivers input that names a `window` (`app.pressKey`, coordinate `app.click`, `scroll`, `drag`, pointer moves, `key_down`/`key_up`) with `XSendEvent`, without activating the window. GTK 4 reads only XInput2 and ignores all of it; Qt ignores the scroll wheel events. Desktop-level calls (no `window`, XTEST) reach every toolkit. LCU interposes on the Sky RPC seam, as the Windows trusted-service wrapper does, and for these two cases only issues the same action through the engine's own desktop-level call:

1. The target window's process is identified (`_NET_WM_PID` through `xprop`, then `/proc/<pid>/maps`): `libgtk-4.so` means GTK 4, `libQt5Core`/`libQt6Core` means Qt. A process that also maps `icudtl.dat`, `libxul.so` or `libffmpeg.so` (Chromium, Electron, Firefox) is never classified as GTK 4. The result is cached per process for ten seconds. Anything unknown (no PID, unreadable maps, another PID namespace) is not translated.
2. For a GTK 4 target, `key`, `click`, `scroll`, `drag`, `move`, `key_down` and `key_up` are translated; for Qt, `scroll` only. `typeText`, `paste`, AT-SPI element actions (`element_id`), screenshots, state and every other app go to the original service unchanged.
3. LCU re-reads `list_windows`. If the target is not listed, is minimized, or the translated point is off screen, the original request is sent and the engine reports its normal result. If the target owns a modal dialog (a transient window listed with `modal: true`), the dialog is focused instead, because the toolkit's grab discards input for its parent.
4. Unless the window is already focused, LCU calls the engine's `activate_window` and waits for the engine to report it focused; if it does not, the call fails with an explicit error rather than sending keys to some other window.
5. Window-relative coordinates become desktop coordinates, `window.x + x` and `window.y + y` (device pixels, the engine's own unit), using geometry read immediately before the call, and the engine's desktop-level `press_key`, `click`, `scroll`, `drag`, `move`, `key_down` or `key_up` runs with the other fields unchanged. The caller gets that call's result, the same shape as before.

Consequences, visible to the user: the target window is raised and focused, and the real pointer moves. GTK 3, Firefox, Chromium, Electron and terminals keep working in the background without either. Translated actions run one at a time.

`LCU_LINUX_INPUT_TRANSLATION=off` (also `0`, `false`, `no`) disables the wrapper; set it in the environment of the `lcu` process as described in the [installation guide](INSTALLATION.md#linux-sandbox-and-input-notes). A tested app/runtime pair in [tested-versions.json](../tested-versions.json) may list `"native_input": ["gtk4", "qt-scroll"]` once the pair itself was verified to handle that toolkit natively; LCU then skips the translation for exactly that pair, and any other version stays translated. See [the adaptation record](STANDALONE-ADAPTATIONS.md) for the evidence and removal criterion.

Tests: `tests/gtk4_input.py` (GTK 4 keys, chords, key hold, click, scroll, drag, a modal dialog, a missing window and the opt-out, with file oracles), `tests/linux_input_controls.py` (GTK 3, a core-event X11 window, a Chromium-like process and Qt keys/click stay on the original path with the focused window unchanged; Qt scroll is translated, with a translation-off control), `tests/adapter_paths.py` (window-targeted GTK 4 keys and click through every adapter path) and the unit tests in `tests/test_runtime.py`.

## Same-case result forwarding

The 2026-09-26 comparison below records Pi 0.73.0, two app-bundled Codex CLI pins, and Claude Code 2.1.204. It measures both host handling and what reaches the model provider. A locally saved audio file is not evidence that audio reached the provider. The latest public standalone Codex CLI has a separate current run in [Codex standalone CLI verification](verification/codex-standalone-cli-2026-09-27.md), and the current public Pi and Claude Code versions have a separate [latest standalone harness verification](verification/latest-standalone-harness-2026-09-27.md); this historical table remains tied to the versions it tested.

| Original result | Pi 0.73.0 | Codex CLI (Mac `0.155.0-alpha.16.3`; Linux `0.155.0-alpha.9.2`) | Claude Code 2.1.204 |
| --- | --- | --- | --- |
| Plain text | Exact text preserved | Exact text preserved on both pinned CLIs | Exact text preserved |
| PNG image | Exact bytes preserved | Exact bytes preserved on both pinned CLIs (`036db0272ba76df7711c9cf4257808effcb0fc3c9e02f9e5d0007060cd497ed5`) | Exact bytes preserved (`036db0272ba76df7711c9cf4257808effcb0fc3c9e02f9e5d0007060cd497ed5`) |
| WAV audio | Exact WAV bytes saved to an absolute local path and returned as `Audio result (original MIME type: audio/wav) saved to <path>`; the provider received the path, not WAV bytes. Saved SHA-256 matches `9d3f06e364a9665a7cd302327f3a84799952d7def702d590a2cdbecd71bab515`. | The Codex relay saved exact WAV bytes to an absolute local path and returned the same MIME/path reference on both pinned CLIs. The provider received the path, not WAV bytes; saved SHA-256 matches `9d3f06e364a9665a7cd302327f3a84799952d7def702d590a2cdbecd71bab515`. | WAV was saved locally byte-for-byte (`9d3f06e364a9665a7cd302327f3a84799952d7def702d590a2cdbecd71bab515`); provider received only a text path/summary, not audio bytes |
| MCP `isError` | Original error text reached the provider; Pi host marked an error, while the provider message had no separate error flag | Original error text reached the provider; host marked `mcp_tool_call` failed, while provider output had no separate error flag | Original error text and native `is_error=true` preserved |

The PNG and WAV hashes identify the shared original fixtures. Provider-facing error representation differs by harness: Pi and Codex carry error text without a separate provider API flag, while Claude preserves its native error field. Exact pinned inputs are recorded in [runtime input evidence](verification/runtime-input-restoration-2026-09-26.md); the run evidence is in [harness results](verification/harness-results-2026-09-26.md).

## Pi extension

The Pi adapter uses Pi's extension API and the shared MCP client. It keeps the connection through model rounds and sends cleanup after the full prompt. Its UI presents original native-app persistence choices and browser-origin requests; headless mode cancels. Current package registration and result forwarding passed with Pi 0.87.1 from `@earendil-works/pi-coding-agent`; see [the standalone host record](verification/latest-standalone-harness-2026-09-27.md). Earlier desktop-task evidence below used Pi 0.73.0.

Pi also registers `/lcu stop` and `/lcu pick`:

```text
/lcu stop
/lcu pick
```

`/lcu stop` requires an interactive Pi session on macOS and an active LCU turn. It lists the original Computer Use apps observed for that turn, asks which app to stop, and sends the exact session, turn, and app identities to the private host-control channel. The host validates the active turn and invokes the installed original Stop method. A task-owned macOS guest verified that the next same-turn action returned the original stopped-for-this-turn error and that the original turn-ended hook recovered a distinct next turn with an exact 39-byte save oracle. LCU sends the original `ComputerUseIPCCodexTurnEndedRequest` with the captured session, turn, and metadata, then retains the existing CLI cleanup notification. Two guest runs accepted Stop while a `type_text` MCP call was pending; that call returned the original stopped-for-this-turn error and a fresh turn completed the 39-byte file oracle. This proves the MCP result and recovery behavior, not interruption of native input at a particular keystroke boundary. The Pi slash-command UI has not been exercised end to end. See the [current Stop verification](verification/headless-stop-implementation-2026-09-27.md).

`/lcu pick` requires Pi's interactive selection and editor APIs and runs only while no LCU turn is active. It selects an original app, browser/profile, and session or open user tab, then appends target guidance to the current editor draft. It does not submit the draft or claim an open user tab. The command is unavailable in headless Pi mode; browser and app availability depends on the original provider. Picker guidance asks the next request to revalidate the selected target, but cannot enforce later model behavior. Installed Pi 0.87.1 source executes registered slash commands inline before its normal streaming queue and its interactive UI can present the selector while the agent is active. Native-app selection passed a live Linux Pi UI smoke test. A separate live browser-tab TUI test on the final 0.4.2 runtime selected an open Chrome extension-provider tab by exact profile and tab identity and inserted guidance into the actual editor draft; it did not submit the draft, claim the tab, or contact a model provider. The `/lcu stop` menu has not been exercised end to end. See [the request-context and picker verification](verification/request-context-2026-09-27.md) for evidence and behavior limits.

A model-driven Linux GTK task and an opt-in official Chrome-extension task are recorded in [Pi verification](verification/pi-generated-gtk-real-model-2026-09-24.md). The [approval scope test](verification/native-app-approval-scopes-2026-09-25.md) verifies response forwarding, not grant persistence across helper restart or revocation. The [dismissal regression](verification/pi-approval-2026-09-26.md) verifies that dismissing an origin prompt cancels it and that an unrelated request is not accepted through an origin allowlist.

## Oh My Pi

Register the experimental OMP integration with `lcu setup --agent omp`. Setup uses OMP's native `plugin link` command on a generated local package. The package contains a wrapper around the Pi adapter with the selected runtime command. OMP profiles receive separate generated packages. Native links are profile-scoped; `--scope project` is rejected because OMP ignores that scope for local links. Setup does not run `pi install` or write Pi settings.

The OMP wrapper connects during asynchronous extension loading and marks its two core tools `loadMode: essential` so OMP advertises them in its first model request. The shared adapter preserves OMP's array of system-prompt blocks and appends the original MCP initialization instructions as a separate block. It uses the common native tool, selection, editor, and lifecycle APIs. Unsupported approval requests cancel. Pi's audio delivery limits also apply. OMP 18.4.1 passed a real model-directed Linux ARM64 GTK save flow with an independent file oracle; see [OMP source and test evidence](verification/omp-compatibility-2026-09-28.md). Browser actions and native OMP approval selection remain unverified.

## Hermes Agent

Register the experimental Hermes integration with `lcu setup --agent hermes`. Setup stages the native Python plugin under the selected profile's `plugins/lcu-cua`, and invokes `hermes plugins enable lcu-cua`. It preserves unrelated Hermes configuration through Hermes's own enable command. Set an absolute `HERMES_HOME` for a named or custom profile. Hermes plugins have profile scope, so `--scope project` is rejected.

The plugin uses a private Node bridge backed by the shared official MCP SDK client. Host lifecycle and request metadata remain outside the model-visible tools. Original native-app approval requests use Hermes's native selector with once, session, and always choices restricted to the scopes the original runtime offers. LCU forwards the selected scope to that runtime and keeps no grant cache. Original browser-origin requests offer once or deny. Unsupported forms and URL approval flows cancel. Images use Hermes's native multimodal result envelope; audio is saved byte-for-byte and represented by a local file reference, as in Pi. The original installed app still supplies execution, schemas, instructions, and permission requests.

Hermes v2026.9.24 (0.21.5) passed a real model-directed Linux ARM64 GTK save flow with an independent file oracle. Its public execution middleware supplies exact turn and call identities omitted by ordinary plugin-handler dispatch. See [Hermes verification](verification/hermes-harness-2026-09-28.md) for source evidence, session isolation, and remaining browser, approval, and platform limits.

## Codex CLI

LCU uses the public standalone Codex CLI found as `codex` on the selected account's `PATH`. Install or update it through the official package, check the command that will run, then register and launch that same command:

```sh
npm install -g @openai/codex@latest
command -v codex
codex --version
/opt/lcu/current/bin/lcu setup --agent codex --yes
codex
```

LCU checks the actual `codex` on `PATH` for the native MCP tool hook type. The installed `0.145.0` public CLI failed that check because its parser rejected `mcp_tool`; the latest public `0.157.1` CLI passed the real tool/result and Stop cleanup fixture. If setup reports an unsupported hook type, update the standalone CLI and rerun setup. The official hooks API supports MCP tool handlers on an existing connection and exposes the Stop, Interrupt, and SubagentStop events used by LCU. LCU keeps `turn_ended` and `js_add_node_module_dir` hidden from model discovery while forwarding Stop cleanup through the original MCP server. The app remains the source for the original CUA runtime and plugin metadata; app-provided components used internally do not replace the public CLI running the Codex session. See the [latest CLI evidence](verification/codex-standalone-cli-2026-09-27.md), the [historical interactive run](verification/codex-interactive-2026-09-24.md), and the [native approval probe](verification/codex-native-approval-2026-09-25.md).

The Codex relay preserves progress before successful and failed tool responses using the SDK's public notification API; the deterministic regression and upstream race are recorded in [Codex progress verification](verification/codex-progress-2026-09-28.md).

## Claude Code adapter

Claude Code uses the official Node runtime, `adapters/claude.mjs`, and the selected LCU command. The relay hides host-internal tools and forwards matching session and prompt IDs to the original runtime. A guarded run verified original Stop cleanup of a temporary Chrome tab. Active-call Escape sent matching original Interrupt; cleanup waited for active JavaScript to finish, a delay also seen with a direct original-runtime client.

The corrected installed relay passed guarded registration and original Chrome Stop cleanup. A current guarded run also cleaned up child A/B turns on their matching stop events and the parent on Stop. A synthetic HTTP 400 fired `StopFailure` with matching session/prompt context, but no original MCP `Interrupt` reached the fixture; Claude reported the failure as `unknown`. See [lifecycle finish evidence](verification/claude-lifecycle-finish-2026-09-26.md). Earlier direct-registration Claude saves predate the relay and do not prove current relay behavior. See also [Claude relay evidence](verification/claude-relay-2026-09-25.md) and the [Claude hook reference](https://code.claude.com/docs/en/hooks).

## Approval boundary

The supported native-app and external Chrome flows have not produced generic schema-field or URL-mode approval requests. Those unobserved shapes are not baseline parity failures. Current tests preserve the original message, origin, and requested native-app persistence scope; a host that cannot present a request fails closed.

Harness approval of LCU's own tools is separate from those requests and is the harness's decision by default. The optional [approval mode](INSTALLATION.md#approval-mode) (`lcu setup --approval auto|ask`) adds or removes only LCU's entries, reversibly:

| Harness | Default | `auto` entry |
| --- | --- | --- |
| Claude Code | asks before each tool call | `permissions.allow: ["mcp__lcu"]`; host-only tools stay in `permissions.deny` |
| Codex CLI | asks before each call (`codex exec` cannot run it under approval policy `never`) | `[mcp_servers.lcu] default_tools_approval_mode = "approve"` |
| Oh My Pi | no prompt in the default `yolo` mode | `tools.approval.js` and `.js_reset` set to `allow`, for profiles in `always-ask` or `write` mode |
| Pi | no permission system | none |
| Hermes | no gate on plugin tools without a `pre_tool_call` hook, which LCU does not register | none |

Manual checks outside the repository fixtures found that Claude Code 2.1.204 auto-approves `mcp__lcu__js` with that rule and denies it without, and that Codex CLI 0.159.3 prompts `Allow the lcu MCP server to run tool "js"?` by default, runs the tool without prompting with the setting, and prompts again once it is removed. `tests/codex_approval_mode.py` reproduces the Codex difference with a scripted provider and an isolated home (run on Codex CLI 0.159.1); the Claude Code and OMP entries are covered by unit tests and no scripted Claude Code or model-driven OMP run is recorded. OMP's key names come from its `tools.approval` setting, which the policy resolver reads by tool name. Entries changed by the mode never include native-app or Chrome approvals, so Chrome site approvals remain exact-origin only.

The [contract audit](verification/harness-contract-audit-2026-09-25.md) records the primary-source review and scope boundaries. Full platform installation steps are in the [installation guide](INSTALLATION.md).
