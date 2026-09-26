# Harness adapters

LCU keeps the original pinned CUA MCP server authoritative. It preserves original tool descriptors, initialization instructions, execution, elicitation, and policy. It does not implement browser control, screenshots, accessibility, input, or JavaScript execution. The shared Pi client and Claude relay use the official MCP SDK; Codex CLI connects to the selected original server directly.

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

The current comparison sends the same original MCP fixtures through Pi 0.73.0, the two app-bundled Codex CLI pins, and Claude Code 2.1.204. It measures both host handling and what reaches the model provider. A locally saved audio file is not evidence that audio reached the provider.

| Original result | Pi 0.73.0 | Codex CLI (Mac `0.155.0-alpha.16.3`; Linux `0.155.0-alpha.9.2`) | Claude Code 2.1.204 |
| --- | --- | --- | --- |
| Plain text | Exact text preserved | Exact text preserved on both pinned CLIs | Exact text preserved |
| PNG image | Exact bytes preserved | Exact bytes preserved on both pinned CLIs (`036db0272ba76df7711c9cf4257808effcb0fc3c9e02f9e5d0007060cd497ed5`) | Exact bytes preserved (`036db0272ba76df7711c9cf4257808effcb0fc3c9e02f9e5d0007060cd497ed5`) |
| WAV audio | Pi returned `Pi cannot represent original CUA audio content`; WAV was not forwarded | The fixture model/provider returned `<audio content omitted because you do not support audio input>` on both pinned CLIs; this is a fixture/configuration result, not an adapter audio rejection | WAV was saved locally byte-for-byte (`9d3f06e364a9665a7cd302327f3a84799952d7def702d590a2cdbecd71bab515`); provider received only a text path/summary, not audio bytes |
| MCP `isError` | Original error text reached the provider; Pi host marked an error, while the provider message had no separate error flag | Original error text reached the provider; host marked `mcp_tool_call` failed, while provider output had no separate error flag | Original error text and native `is_error=true` preserved |

The PNG and WAV hashes identify the shared original fixtures. Provider-facing error representation differs by harness: Pi and Codex carry error text without a separate provider API flag, while Claude preserves its native error field. Exact pinned inputs are recorded in [runtime input evidence](verification/runtime-input-restoration-2026-09-26.md); the run evidence is in [harness results](verification/harness-results-2026-09-26.md).

## Pi extension

Pi 0.73 uses its extension API and the shared MCP client. It keeps the connection through model rounds and sends cleanup after the full prompt. Its UI presents original native-app persistence choices and browser-origin requests; headless mode cancels. The [Pi extension API](https://github.com/badlogic/pi-mono/blob/v0.73.0/packages/coding-agent/docs/extensions.md) documents its UI and tool-result types.

A model-driven Linux GTK task and an opt-in official Chrome-extension task are recorded in [Pi verification](verification/pi-generated-gtk-real-model-2026-09-24.md). The [approval scope test](verification/native-app-approval-scopes-2026-09-25.md) verifies response forwarding, not grant persistence across helper restart or revocation. The [dismissal regression](verification/pi-approval-2026-09-26.md) verifies that dismissing an origin prompt cancels it and that an unrelated request is not accepted through an origin allowlist.

## Codex CLI

Codex CLI registration checks the installed executable for the original `mcp_tool` lifecycle-hook support. Setup does not select or replace the Codex executable. Use the tested app-bundled CLI explicitly on `PATH` for both setup and launch; on Linux:

```sh
PATH="/opt/lcu/current/app/resources:$PATH" /opt/lcu/current/bin/lcu setup --agent codex --yes
PATH="/opt/lcu/current/app/resources:$PATH" codex
```

The tested bundled versions are `0.155.0-alpha.16.3` on macOS and `0.155.0-alpha.9.2` on Linux. The ordinary `0.145.0` CLI failed the hook parser check; these results do not establish a minimum stable public version. The [interactive run](verification/codex-interactive-2026-09-24.md) records native GTK and Chrome actions, exact site approval, and Stop/Interrupt cleanup. The [native approval probe](verification/codex-native-approval-2026-09-25.md) verifies response serialization, not a Codex CLI grant cache.

## Claude Code adapter

Claude Code uses the official Node runtime, `adapters/claude.mjs`, and the selected LCU command. The relay hides host-internal tools and forwards matching session and prompt IDs to the original runtime. A guarded run verified original Stop cleanup of a temporary Chrome tab. Active-call Escape sent matching original Interrupt; cleanup waited for active JavaScript to finish, a delay also seen with a direct original-runtime client.

The corrected installed relay passed guarded registration and original Chrome Stop cleanup. A current guarded run also cleaned up child A/B turns on their matching stop events and the parent on Stop. A synthetic HTTP 400 fired `StopFailure` with matching session/prompt context, but no original MCP `Interrupt` reached the fixture; Claude reported the failure as `unknown`. See [lifecycle finish evidence](verification/claude-lifecycle-finish-2026-09-26.md). Earlier direct-registration Claude saves predate the relay and do not prove current relay behavior. See also [Claude relay evidence](verification/claude-relay-2026-09-25.md) and the [Claude hook reference](https://code.claude.com/docs/en/hooks).

## Approval boundary

The supported native-app and external Chrome flows have not produced generic schema-field or URL-mode approval requests. Those unobserved shapes are not baseline parity failures. Current tests preserve the original message, origin, and requested native-app persistence scope; a host that cannot present a request fails closed.

The [contract audit](verification/harness-contract-audit-2026-09-25.md) records the primary-source review and scope boundaries. Full platform installation steps are in the [installation guide](INSTALLATION.md).
