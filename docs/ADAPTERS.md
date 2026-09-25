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

The command above starts native computer use only. To opt a direct client into Chrome, append `--chrome` to the `lcu` command after the `lcu-session` separator, and first configure the account's native host with `lcu browser install`. That native-host command does not install the Web Store extension; the user must enable the official extension in the intended Chrome profile. The host must supply its actual session and active turn IDs, keep one connection alive through that turn, show the server's initialization instructions and installed local full LCU skill before the first computer-use call, and pass the original tool result content to its model. `publicTools()` exposes the exact upstream `js` and `js_reset` descriptions and JSON schemas. `js_add_node_module_dir` and `turn_ended` remain host-only. An adapter must call `turnEnded` after a completed or interrupted agent turn; closing a transport does not substitute for cleanup.

In Chrome mode the original browser service requests an MCP `elicitation/create` decision when an origin needs approval. The client advertises form elicitation and delegates that request to `onElicitation`. No callback means `cancel`. A host may pass `allowedOrigins: ['https://example.com']` only for origins the user explicitly preauthorized. These are exact HTTP(S) origins, not patterns; only a request marked by the original provider as `access_browser_origin` for that same origin is accepted automatically. Other approval requests still reach `onElicitation` or fail closed. The host must not infer permission from the page, from the model's proposed action, or from a broad network allowlist. LCU delivers original unified CUA instructions in this mode. The separate byte-identical `control-chrome` plugin skill remains a reference, not a standalone plugin adapter supplied by LCU.

## Pi extension

Pi 0.73's extension API supports tools, `before_agent_start` system prompt additions, UI confirmation, and `agent_start`/`agent_end` events. Its `turn_end` fires after each assistant model round, so LCU cleanup uses `agent_end` after the full prompt. Session switch, fork, and shutdown emit `session_shutdown` for the old extension instance. That event and an aborted agent prompt invoke interruption cleanup. The Pi extension retains the same MCP connection and turn ID through successive model rounds. Pi provides a real session UUID; the extension assigns a unique turn ID when Pi emits the actual `agent_start` event.

The normal first-run path is `lcu setup --agent pi --yes` in the target account, followed by `pi`. This configures native computer use only; add `--chrome` to that setup command to opt into the original extension path. Setup uses Pi's local package installer to register one account-local extension and installs the generated full LCU skill. `--session direct` and `--session discover` are stored in account-owned `~/.local/share/lcu/pi/commands.json`; its project commands are keyed by the exact canonical project path selected during setup. Both scopes register the same extension source, so Pi's project package precedence loads it once. A repository file cannot substitute a runtime command. Pi itself must already be installed on the target account's `PATH`. If a privileged installer cannot see a user-managed Pi executable, run `lcu setup --agent pi --yes` from that user's shell after installing the runtime. The portable export contains only a bootstrap.

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

A separate [natural-language Pi run](verification/pi-generated-gtk-real-model-2026-09-24.md) used the generated Linux skill, release adapter and existing `zai/glm-4.5-air` provider to set and save a draft in an isolated GTK Target window. The independent file oracle matched, and the Other window stayed untouched. With the platform-correct Linux skill, a later native turn also saved its exact marker. An opt-in Chrome turn used the original extension to save an exact loopback fixture value with its agent request header; a second turn left a temporary tab open and Pi's automatic `turn_ended` cleanup closed it. That Chrome run explicitly preauthorized the bounded origin through `LCU_APPROVED_ORIGINS`. A separate [real Pi terminal run](verification/pi-origin-dialog-2026-09-25.md) accepted an exact loopback-origin prompt from an MCP SDK fixture with a scripted provider. The dialog run verifies interactive rendering and acceptance, not original Chrome behavior or a model-driven browser action.

## Codex CLI

LCU setup registers the original MCP tools, full local skill and the pinned plugin's `Stop`, `Interrupt` and `SubagentStop` `mcp_tool` hooks. The hidden `turn_ended` tool is omitted from model tool discovery; the host invokes it with real session and turn metadata. The target Codex CLI must parse this original hook type. Setup checks an installed `codex` executable in an empty temporary home before changing the target configuration and reports its path/version if it lacks hook support. The tested ordinary CLI `0.145.0` fails that check. The pinned macOS app's `/Applications/ChatGPT.app/Contents/Resources/codex` (`0.155.0-alpha.16.3`), both pinned Linux apps' `/opt/lcu/current/app/resources/codex` (`0.155.0-alpha.9.2`), and the pinned Windows app's privately staged `codex.exe` (`0.155.0-alpha.16.4`) pass the no-auth parser check; only the macOS bundled CLI was used for the interactive model task. These results do not establish a minimum public stable version. If Codex CLI is not yet installed, setup can register LCU, but the eventual host must support these hooks before use.

For the verified app-bundled CLI, put its resource directory on `PATH` for both setup and launch, then use the same `codex` executable. For example, with the default Linux prefix:

```sh
PATH="/opt/lcu/current/app/resources:$PATH" /opt/lcu/current/bin/lcu setup --agent codex --yes
PATH="/opt/lcu/current/app/resources:$PATH" codex
```

On Apple Silicon macOS, use the tested bundled executable from the signed app:

```sh
PATH="/Applications/ChatGPT.app/Contents/Resources:$PATH" /absolute/path/to/lcu/bin/lcu setup --agent codex --yes
PATH="/Applications/ChatGPT.app/Contents/Resources:$PATH" codex
```

LCU does not change `PATH` or silently substitute a CLI executable. The [current Linux archive gate](verification/final-linux-gates-2026-09-24.md) records both installed parser probes.

[Interactive model evidence](verification/codex-interactive-2026-09-24.md) covers generated Linux skill delivery, a saved native GTK Target draft with an independent file oracle, an opt-in original Chrome-extension Save with exact site approval and the extension request header, real Stop/Interrupt hook dispatch, and an unmarked temporary tab closed on Stop. The tests used a disposable Linux ARM64 desktop and a local container relay for the project MCP command; they did not use a personal desktop or broader host MCP configuration. Both CLI and app runtime were pinned as recorded there.

## Claude Code lifecycle boundary

Current Claude Code setup registers the original MCP server and skill and adds exact deny rules for the host-only `turn_ended` and `js_add_node_module_dir` tools while preserving unrelated settings. It does not install a hook or adapter that calls original `turn_ended` on normal completion or interruption. A guarded Claude Code 2.1.204 CLI run against a local scripted provider verified that the actual model request exposed only `js` and `js_reset`, two original JavaScript calls shared state, and normal completion fired `PreToolUse`, `PostToolUse`, `MessageDisplay`, and `Stop`. This was a scripted host test, not a Claude model-driven desktop task. A running 30-second original JavaScript call was interrupted with Esc; the CLI returned to its prompt, and no completion, failure, or session-end hook fired at that point. A later read proved the call had started. The original MCP request metadata contained LCU's synthetic connection fallback ID pair, which differed from Claude's hook session and displayed turn IDs. Thus even normal `Stop` cannot safely call original `turn_ended` with a matching pair in the current direct registration. Claude's documented [MCP-tool hooks](https://code.claude.com/docs/en/hooks#MCP-tool-hook-fields) supply `tool_use_id`, but the observed hooks supplied no matching `turn_id`; `MessageDisplay` runs only when text is rendered. The documented `Stop` hook [does not fire on user interruption](https://code.claude.com/docs/en/hooks). The installed Windows LCU candidate proved that a direct original `turn_ended` call removes its native helper on matching Stop or Interrupt, and that a stale Stop leaves newer work intact; Claude's missing host dispatch therefore matters for Windows native use as well as opt-in Chrome temporary tabs. Native Windows execution through Claude Code itself has not been tested. LCU does not manufacture lifecycle events from prompt submission. Use Pi or a compatible Codex CLI when automatic per-turn cleanup is required. [The probe record](verification/claude-lifecycle-2026-09-24.md) gives the observed events and limits. See [Claude Code MCP documentation](https://code.claude.com/docs/en/mcp) for its host UI behavior.

A [guarded real-model probe](verification/claude-glm-2026-09-25.md) used Claude Code 2.1.204 with Z.ai GLM 5.3 Flash. Claude rendered and returned the original native app-access elicitation, and a declined request blocked the action. Later fixture tests passed original Linux GTK and macOS AppKit saves, each with an independent file oracle. Earlier Linux X11 and macOS TextEdit timeout failures did not reproduce in those fixtures; their causes remain unknown. Claude per-turn cleanup is still unwired. Anthropic documents automatic [MCP elicitation dialogs](https://code.claude.com/docs/en/mcp#respond-to-mcp-elicitation-requests); no separate LCU approval UI was added.

## Earlier exploratory model runs

The first Codex native save used temporary MCP configuration without the generated skill. A later native Chrome-window fallback saved a local page without the extension header; it was not evidence of the original extension API. Another headless Codex run declined the original site request because that host mode could not present the approval. A separate Pi invocation with `openai-codex/gpt-5.5` received HTTP 401 before a model response. These failures drove the generated-skill, interactive-origin and existing-provider tests above; none is counted as current extension or Pi native success evidence.
