# Harness adapters

LCU keeps the original pinned CUA MCP server authoritative for instructions, execution, elicitation, policy, and lifecycle. It does not implement browser control, screenshots, accessibility, input, or JavaScript execution. The Pi client, Claude relay, and Codex relay use the official MCP SDK. The Codex relay passes original initialization instructions and public `js`/`js_reset` descriptors through, but intentionally omits `js_add_node_module_dir` and `turn_ended` from model-visible `tools/list`. It still forwards host calls to those original tools; the installed Codex Stop hook reaches `turn_ended` with the original session and turn IDs. This is an explicit visibility adaptation, not full `tools/list` parity.

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

Before the first CUA call, the host must load the generated full local LCU skill as well as the original initialization instructions and public tool descriptors into model context. Forward original result content and error state unchanged. Keep one connection alive through the turn and use real host session/turn IDs. `turn_ended`, `js_add_node_module_dir`, and Claude's `set_turn_context` are host-only tools; do not expose them to the model. Invoke original cleanup only for lifecycle events the host reports. The shared client cancels unresolved elicitation when `onElicitation` is absent. Otherwise, render the original request and return the user's actual response. `allowedOrigins` is only for exact HTTP(S) origins the user explicitly approved. LCU keeps no permission cache.

## Same-case result forwarding

The 2026-09-26 comparison below records Pi 0.73.0, two app-bundled Codex CLI pins, and Claude Code 2.1.204. It measures both host handling and what reaches the model provider. A locally saved audio file is not evidence that audio reached the provider. The latest public standalone Codex CLI has a separate current run in [Codex standalone CLI verification](verification/codex-standalone-cli-2026-09-27.md); this historical table remains tied to the versions it tested.

| Original result | Pi 0.73.0 | Codex CLI (Mac `0.155.0-alpha.16.3`; Linux `0.155.0-alpha.9.2`) | Claude Code 2.1.204 |
| --- | --- | --- | --- |
| Plain text | Exact text preserved | Exact text preserved on both pinned CLIs | Exact text preserved |
| PNG image | Exact bytes preserved | Exact bytes preserved on both pinned CLIs (`036db0272ba76df7711c9cf4257808effcb0fc3c9e02f9e5d0007060cd497ed5`) | Exact bytes preserved (`036db0272ba76df7711c9cf4257808effcb0fc3c9e02f9e5d0007060cd497ed5`) |
| WAV audio | Exact WAV bytes saved to an absolute local path and returned as `Audio result (original MIME type: audio/wav) saved to <path>`; the provider received the path, not WAV bytes. Saved SHA-256 matches `9d3f06e364a9665a7cd302327f3a84799952d7def702d590a2cdbecd71bab515`. | The Codex relay saved exact WAV bytes to an absolute local path and returned the same MIME/path reference on both pinned CLIs. The provider received the path, not WAV bytes; saved SHA-256 matches `9d3f06e364a9665a7cd302327f3a84799952d7def702d590a2cdbecd71bab515`. | WAV was saved locally byte-for-byte (`9d3f06e364a9665a7cd302327f3a84799952d7def702d590a2cdbecd71bab515`); provider received only a text path/summary, not audio bytes |
| MCP `isError` | Original error text reached the provider; Pi host marked an error, while the provider message had no separate error flag | Original error text reached the provider; host marked `mcp_tool_call` failed, while provider output had no separate error flag | Original error text and native `is_error=true` preserved |

The PNG and WAV hashes identify the shared original fixtures. Provider-facing error representation differs by harness: Pi and Codex carry error text without a separate provider API flag, while Claude preserves its native error field. Exact pinned inputs are recorded in [runtime input evidence](verification/runtime-input-restoration-2026-09-26.md); the run evidence is in [harness results](verification/harness-results-2026-09-26.md).

## Pi extension

Pi 0.73 uses its extension API and the shared MCP client. It keeps the connection through model rounds and sends cleanup after the full prompt. Its UI presents original native-app persistence choices and browser-origin requests; headless mode cancels. The [Pi extension API](https://github.com/badlogic/pi-mono/blob/v0.73.0/packages/coding-agent/docs/extensions.md) documents its UI and tool-result types.

A model-driven Linux GTK task and an opt-in official Chrome-extension task are recorded in [Pi verification](verification/pi-generated-gtk-real-model-2026-09-24.md). The [approval scope test](verification/native-app-approval-scopes-2026-09-25.md) verifies response forwarding, not grant persistence across helper restart or revocation. The [dismissal regression](verification/pi-approval-2026-09-26.md) verifies that dismissing an origin prompt cancels it and that an unrelated request is not accepted through an origin allowlist.

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

## Claude Code adapter

Claude Code uses the official Node runtime, `adapters/claude.mjs`, and the selected LCU command. The relay hides host-internal tools and forwards matching session and prompt IDs to the original runtime. A guarded run verified original Stop cleanup of a temporary Chrome tab. Active-call Escape sent matching original Interrupt; cleanup waited for active JavaScript to finish, a delay also seen with a direct original-runtime client.

The corrected installed relay passed guarded registration and original Chrome Stop cleanup. A current guarded run also cleaned up child A/B turns on their matching stop events and the parent on Stop. A synthetic HTTP 400 fired `StopFailure` with matching session/prompt context, but no original MCP `Interrupt` reached the fixture; Claude reported the failure as `unknown`. See [lifecycle finish evidence](verification/claude-lifecycle-finish-2026-09-26.md). Earlier direct-registration Claude saves predate the relay and do not prove current relay behavior. See also [Claude relay evidence](verification/claude-relay-2026-09-25.md) and the [Claude hook reference](https://code.claude.com/docs/en/hooks).

## Approval boundary

The supported native-app and external Chrome flows have not produced generic schema-field or URL-mode approval requests. Those unobserved shapes are not baseline parity failures. Current tests preserve the original message, origin, and requested native-app persistence scope; a host that cannot present a request fails closed.

The [contract audit](verification/harness-contract-audit-2026-09-25.md) records the primary-source review and scope boundaries. Full platform installation steps are in the [installation guide](INSTALLATION.md).
