# Harness adapters

LCU's adapter package connects a harness to the installed original CUA MCP server. It does not implement browser, desktop, screenshot, accessibility, or JavaScript execution. The supplied command launches the selected LCU runtime on its own machine. `adapters/client.mjs` uses the official `@modelcontextprotocol/sdk` 1.30.0 client and stdio transport; `adapters/package-lock.json` pins its dependencies.

## Common client contract

```js
import { createCuaClient } from './adapters/client.mjs';

const cua = createCuaClient({
  command: ['/absolute/path/to/lcu-session', '--user', 'alice', '--', '/absolute/path/to/lcu'],
  onElicitation: async params => {
    // Present the exact requested origin to the user. Return their decision.
    return { action: 'cancel' };
  },
});
await cua.connect();
const instructions = cua.instructions;
const modelTools = cua.publicTools(); // upstream js and js_reset descriptors
const result = await cua.call('js', { code: 'await cua.getState()' }, {
  sessionId: hostSessionId, turnId: activeHostTurnId,
});
await cua.turnEnded({ sessionId: hostSessionId, turnId: activeHostTurnId, event: 'Stop' });
await cua.close();
```

The host must supply its actual session and active turn IDs, keep one connection alive through that turn, show the server's initialization instructions and installed local full LCU skill before the first computer-use call, and pass the original tool result content to its model. `publicTools()` exposes the exact upstream `js` and `js_reset` descriptions and JSON schemas. `js_add_node_module_dir` and `turn_ended` remain host-only. An adapter must call `turnEnded` after a completed or interrupted agent turn; closing a transport does not substitute for cleanup.

The original browser service requests an MCP `elicitation/create` decision when an origin needs approval. The client advertises form elicitation and delegates that request to `onElicitation`. No callback means `cancel`. A host may pass `allowedOrigins: ['https://example.com']` only for origins the user explicitly preauthorized. These are exact HTTP(S) origins, not patterns; only a request marked by the original provider as `access_browser_origin` for that same origin is accepted automatically. Other approval requests still reach `onElicitation` or fail closed. The host must not infer permission from the page, from the model's proposed action, or from a broad network allowlist.

## Pi extension

Pi 0.73's extension API supports tools, `before_agent_start` system prompt additions, UI confirmation, and `agent_start`/`agent_end` events. Its `turn_end` fires after each assistant model round, so LCU cleanup uses `agent_end` after the full prompt. Session switch, fork, and shutdown emit `session_shutdown` for the old extension instance. That event and an aborted agent prompt invoke interruption cleanup. The Pi extension retains the same MCP connection and turn ID through successive model rounds. Pi provides a real session UUID; the extension assigns a unique turn ID when Pi emits the actual `agent_start` event.

Install adapter dependencies with `npm ci --prefix adapters --ignore-scripts`. Generate the full account-local LCU skill on the target machine with `lcu setup`; the portable export contains only a bootstrap. Then launch Pi with a supplied command, for example:

```sh
LCU_MCP_COMMAND='["/opt/lcu/current/bin/lcu-session","--user","alice","--","/opt/lcu/current/bin/lcu"]' \
  pi -e /absolute/lcu/adapters/pi/index.ts \
  --skill /home/alice/.local/share/lcu/skills/lcu/SKILL.md
```

For a Pi backend already inside the intended desktop session, supply the direct `lcu` command instead. `LCU_APPROVED_ORIGINS` may contain an explicit JSON array of user-approved exact origins. With no such array, Pi asks the user through its UI for each unresolved origin. It also presents other original approval requests that use an empty form, such as history or native access, with the exact server message. In print or headless mode it cancels; it never silently grants access. URL-mode and nonempty forms, including secure credential entry, currently cancel because Pi's basic confirmation dialog cannot represent them faithfully.

Pi tool results support text and images. The extension passes original text and image blocks through and retains the full MCP result in `details.originalResult`. Pi has no audio, resource-link, or embedded-resource tool-result block, so those original results raise visible errors. Pi also has no way to preserve MCP `isError` with its original content blocks: the extension raises an error using the original text instead of presenting a failed MCP result as a successful tool call. This is a Pi result-type boundary, not a change to the common client.

Primary source checked: installed `@mariozechner/pi-coding-agent` 0.73.0 `docs/extensions.md`, `dist/core/extensions/types.d.ts`, and `docs/sdk.md` (custom tools, dynamic registration, agent/session events, UI); Pi's tool result types permit text and images. The pinned original unified-computer-use plugin hook manifest supplies the Stop/Interrupt/SubagentStop `turn_ended` inputs. The original browser service remains the authority for origin policy and saved approval decisions.

The adapter suite includes an installed Pi 0.73 test using an isolated home, local scripted OpenAI-compatible endpoint, and SDK-backed MCP fixture. It verifies that Pi's model request includes the original tool descriptions and initialization guide, discovers the supplied skill, calls `js` twice across model rounds with one session/turn ID, and invokes `turn_ended` once at prompt completion. No paid model or personal desktop is involved. With `LCU_REAL_COMMAND='["/absolute/lcu"]'`, two additional tests connect to the selected installed original MCP server: one checks instructions, schemas, persistent pure JavaScript, cleanup and reset; the other runs installed Pi with that server and a local scripted model, checking actual original tool and guide delivery plus two persistent arithmetic calls. They use isolated child homes and make no desktop or browser call. These tests passed against the selected macOS 26.917.62051 application on 2026-09-24. The same tests remain required on selected Linux builds; these pure JavaScript results do not prove desktop or Chrome action behavior.
