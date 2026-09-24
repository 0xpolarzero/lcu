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

The normal first-run path is `lcu setup --agent pi --yes` in the target account, followed by `pi`. Setup uses Pi's local package installer to register one account-local extension and installs the generated full LCU skill. `--session direct` and `--session discover` are stored in account-owned `~/.local/share/lcu/pi/commands.json`; its project commands are keyed by the exact canonical project path selected during setup. Both scopes register the same extension source, so Pi's project package precedence loads it once. A repository file cannot substitute a runtime command. Pi itself must already be installed on the target account's `PATH`. If a privileged installer cannot see a user-managed Pi executable, run `lcu setup --agent pi --yes` from that user's shell after installing the runtime. The portable export contains only a bootstrap.

For an explicit one-off launch, install adapter dependencies with `npm ci --prefix adapters --ignore-scripts` and supply a command:

```sh
LCU_MCP_COMMAND='["/opt/lcu/current/bin/lcu-session","--user","alice","--","/opt/lcu/current/bin/lcu"]' \
  pi -e /absolute/lcu/adapters/pi/index.ts \
  --skill /home/alice/.local/share/lcu/skills/lcu/SKILL.md
```

For a Pi backend already inside the intended desktop session, supply the direct `lcu` command instead. `LCU_MCP_COMMAND` remains an explicit override of the setup-selected command. `LCU_APPROVED_ORIGINS` may contain an explicit JSON array of user-approved exact origins. With no such array, Pi asks the user through its UI for each unresolved origin. It also presents other original approval requests that use an empty form, such as history or native access, with the exact server message. In print or headless mode it cancels; it never silently grants access. URL-mode and nonempty forms, including secure credential entry, currently cancel because Pi's basic confirmation dialog cannot represent them faithfully.

Pi tool results support text and images. The extension passes original text and image blocks through and retains the full MCP result in `details.originalResult`. Pi has no audio, resource-link, or embedded-resource tool-result block, so those original results raise visible errors. Pi also has no way to preserve MCP `isError` with its original content blocks: the extension raises an error using the original text instead of presenting a failed MCP result as a successful tool call. This is a Pi result-type boundary, not a change to the common client.

Primary source checked: installed `@mariozechner/pi-coding-agent` 0.73.0 `docs/extensions.md`, `dist/core/extensions/types.d.ts`, and `docs/sdk.md` (custom tools, dynamic registration, agent/session events, UI); Pi's tool result types permit text and images. The pinned original unified-computer-use plugin hook manifest supplies the Stop/Interrupt/SubagentStop `turn_ended` inputs. The original browser service remains the authority for origin policy and saved approval decisions.

The adapter suite includes an installed Pi 0.73 test using an isolated home, local scripted OpenAI-compatible endpoint, and SDK-backed MCP fixture. It verifies that Pi's model request includes the original tool descriptions and initialization guide, discovers the supplied skill, calls `js` twice across model rounds with one session/turn ID, and invokes `turn_ended` once at prompt completion. No paid model or personal desktop is involved. With `LCU_REAL_COMMAND='["/absolute/lcu"]'`, two additional tests connect to the selected installed original MCP server: one checks instructions, schemas, persistent pure JavaScript, cleanup and reset; the other installs the same local extension source in Pi user and project scopes, provides an invalid account command, a valid registered project command, and a malicious unregistered repository command file, then verifies Pi loads one original tool/guide and completes two persistent arithmetic calls through the registered project command. These tests use isolated child homes and make no desktop or browser call. They passed against the selected macOS 26.917.62051 application and selected Linux ARM64 original runtime on 2026-09-24; these pure JavaScript results do not prove desktop or Chrome action behavior.

## Claude Code lifecycle boundary

Claude Code natively loads MCP servers and skills and presents MCP elicitation. Its documented `Stop` hook fires when an assistant response finishes, but [does not fire on user interruption](https://code.claude.com/docs/en/hooks). `SessionEnd` fires when the whole session exits, not when a prompt is interrupted; `StopFailure` covers API errors. Therefore the native Claude registration delivers original tools and instructions and lets Claude show original approval requests, but cannot report every original `Interrupt` event or guarantee per-prompt cleanup on Ctrl-C. LCU does not manufacture lifecycle events from prompt submission. The locally installed `claude` launcher was intentionally guarded against automated model runs, so this integration has configuration and fixture evidence, not a live Claude model result. See [Claude Code MCP documentation](https://code.claude.com/docs/en/mcp) for its host UI behavior.

## Model-driven fixture evidence

On 2026-09-24, a locally authenticated Codex CLI model received a natural-language task to set the draft in the `LCU Target` GTK window to `Model-driven LCU verified`, save it, and leave `LCU Other` alone. It called LCU's original `js` tool in a named, network-disabled ARM64 Linux container. After self-correcting an initial window-selection error, it read AT-SPI state, entered the text, clicked Save, and reported the UI's `Saved: Model-driven LCU verified` confirmation. The independent fixture file `Target.txt` held the exact value, `Other.txt` was absent, and the fixture error log was empty. The Codex run used temporary MCP command configuration and original MCP instructions; it did not load a generated LCU skill or exercise a user's normal installed Codex setup. The first attempt on a separate container failed Save because that test fixture lacked its required `LCU_TEST_OUTPUT` variable, causing `KeyError` in the fixture's own callback. The corrected run resolved that setup error without changing LCU.

A separate natural-language Codex task opened the local `http://127.0.0.1:8080/` page through LCU's native Chrome-window controls, entered `Browser model LCU verified`, clicked Save, read the visible `Saved` state, and captured screenshots. The local server independently recorded the save request and value. This was **not** an original Chrome-extension browser API success: `createBrowserTab` failed with `Codex auth token is unavailable`, the saved-page requests had no `x-browser-agent` header, and no origin elicitation was reached. That attempt used an older disposable browser image. A second run with explicit browser-provider environment failed earlier with `failed to start Node runtime`; it did not open a page.

One final model attempt used a fresh install of the integrated ARM64 archive in the disposable Chrome image, with the runtime's default browser environment. Codex CLI again received `failed to start Node runtime` on `createBrowserTab`, including after one reset, before any page request or approval prompt. In the same container, a direct MCP fixture client listed the original Chrome extension and successfully opened that localhost tab; its approval callback received three requests scoped to the local fixture. The final scripted Chrome differential also passed without a browser environment override. This isolates the remaining model-driven extension failure to the Codex CLI host path in this test configuration. It does not establish a model-driven origin approval, extension save, or extension cleanup. The generated local LCU skill was not loaded in these temporary Codex CLI runs.
