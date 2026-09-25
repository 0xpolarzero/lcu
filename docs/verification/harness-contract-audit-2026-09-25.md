# Harness integration contract audit, 2026-09-25

## Current evidence

Claude Code 2.1.204 with Z.ai GLM 5.3 Flash completed independent, model-driven saves through original LCU tools on generated Linux GTK and macOS AppKit fixtures. See [the Claude/GLM verification record](claude-glm-2026-09-25.md). The earlier Linux X11 error and macOS TextEdit timeout remain unexplained. Claude still lacks verified per-turn cleanup wiring. These results establish the current native-task path, not complete host parity.

This audit separates the original CUA runtime contract from the host harness contract. It does not propose replacing original computer-use, browser, accessibility, or operating-system behavior.

## Existing integration shape

| Area | Present evidence |
|---|---|
| Original API and guidance | The installed original MCP server remains authoritative for tool descriptions, schemas, initialization instructions, execution and policy. The full generated LCU skill supplies platform-specific operating guidance. `adapters/client.mjs` filters only host-only `js_add_node_module_dir` and `turn_ended`; it leaves the original public `js` and `js_reset` descriptors intact. |
| Host integration | Pi uses the shared official-SDK stdio client and extension. Codex CLI and Claude Code currently register the original MCP server directly with the generated skill; they do not use the Pi adapter or a shared mediation process. See [adapter details](../ADAPTERS.md), `lcu/setup_clients.py`, and `lcu/claude_visibility.py`. |
| Identity and cleanup | The shared client requires the host's actual session and active turn IDs, attaches them to original tool calls, supports abort signals, and exposes `turnEnded`. Pi has tested completion/interruption cleanup. Codex CLI's tested hooks provide Stop, Interrupt, and SubagentStop. Claude's current registration does not produce matching original `turn_ended` events; its lifecycle limitation is documented in [the Claude lifecycle probe](claude-lifecycle-2026-09-24.md). |
| Results | The Pi adapter preserves original text and image blocks and surfaces original tool errors. It reports unsupported audio/resource result types as errors. Codex and Claude direct integrations receive original MCP results; this audit does not establish complete rich-content behavior in every model UI. |
| Permissions and sandbox | The runtime and native helper remain the decision authority for computer-use policy and OS privacy permissions. Host adapters must preserve configured launch command, environment, and sandbox boundary; they must not fabricate grants or infer permission from model intent. Native OS dialogs remain the original helper/OS responsibility. |
| Browser | Optional external Chrome is an original extension path, gated by the original browser service's site policy. It is not an embedded browser or IAB. Original site/origin approval remains baseline; secure `browserAuth` credential input is conditional on a backend-advertised capability and is not proven available on Chrome. Chrome retention marks are not a handoff UI. See `adapters/client.mjs` and the browser section of [adapter details](../ADAPTERS.md). |

## Approval semantics

An MCP tool permission and the original CUA app/site elicitation are separate decisions. Claude's outer tool permissions govern whether Claude may call an MCP tool; Claude's [MCP elicitation UI](https://code.claude.com/docs/en/mcp#respond-to-mcp-elicitation-requests) renders server requests for user input. Its [permissions documentation](https://code.claude.com/docs/en/permissions) describes tool allow/deny behavior. The MCP specification defines form elicitation responses as accept, decline, or cancel with submitted content; it does not define an approval-memory policy ([MCP elicitation, 2025-11-25](https://modelcontextprotocol.io/specification/2025-11-25/client/elicitation)).

Original macOS app policy requests elicitation for each protected operation and can attach `_meta.persist` scopes `session` and, when policy allows, `always`; see the pinned original `@oai/sky/dist/project/cua/sky_js/src/targets/mac/computer-use-policy.js` and [the helper investigation](macos-helper-timeout-2026-09-25.md). The installed original runtime honored these response scopes in generated-app checks: `session` reused approval across protected actions and a later turn, while `always` suppressed elicitation on a fresh MCP bridge with a different session ID. The [scope verification](native-app-approval-scopes-2026-09-25.md) records the test boundary and unverified helper-restart/revocation behavior. Pi now presents only the persistence scopes in the request through `ctx.ui.select` and returns the selection in the original MCP response; it does not cache native grants (`adapters/client.mjs`, `adapters/pi/index.ts`). Its `LCU_APPROVED_ORIGINS` exact allowlist is a separate browser-origin policy. URL and nonempty forms remain unsupported by Pi's basic dialogs.

Codex CLI's real-model evidence covers Chrome site approval with **Allow once**, not remembered native-app approval. Its separate native approval fixture now verifies TUI response serialization, but not grant reuse. Codex desktop has a separate session approval handler; that desktop behavior does not establish Codex CLI behavior. Claude's earlier built-in elicitation UI successfully rendered Accept/Decline and native saves passed, but the sanitized transcript does not preserve raw persistence metadata or responses; a repeated prompt appeared. Do not claim session/always memory for Codex CLI or Claude from those host observations.

The original skill's sensitive-action confirmation guidance is distinct from a host's access grant. A model following that guidance does not replace an app/site permission decision, and an access grant does not authorize every sensitive action. Optional credential-entry forms are not a demonstrated baseline gap where current LCU policies do not request them.

## Proposed harness contract

The shared platform boundary should stay small and preserve upstream behavior:

1. Launch the selected original runtime with the configured command, environment, and sandbox intact; reuse the host's transport or the official MCP SDK. Do not add a second automation or MCP protocol implementation, or invent Claude interrupt events.
2. Keep original public tools, schemas, initialization instructions, generated skill, and returned documentation visible to the model. Hide only host-internal tools. Preserve text and image output; surface errors and unsupported content explicitly.
3. Bind every call to the host's real session and turn identity. Forward cancellation. Send one matching completion, interruption, or child-turn cleanup event only when the host actually exposes it; make cleanup idempotent and report hosts without a reliable event.
4. Route original elicitation requests to the harness's existing UI. Preserve exact message, requested form, and metadata. Return the user's actual accept/decline/cancel decision and form content. Keep outer tool approval, original app/site access, OS privacy, and sensitive-action guidance distinct.
5. For the original native-app approval form, show only persistence scopes listed by the original request and return the user's selected scope in the original MCP elicitation response. Let the original runtime apply its native memory behavior; do not add an LCU grant store or infer a grant from missing metadata. Keep this policy separate from browser-origin preauthorization.
6. Leave computer-use execution, browser policy, screenshots, accessibility, native OS prompts, and application interaction to the original runtime and platform helper.

Credential prompts, URL handoff, cloud-user verification, and richer content types should be handled only when an actual original policy or supported host workflow requires them; their absence is not, by itself, a parity failure for current LCU use.

## Primary sources

- Local implementation: `adapters/client.mjs`, `adapters/pi/index.ts`, `lcu/setup_clients.py`, `lcu/codex_hooks.py`, `lcu/claude_visibility.py`.
- Local evidence: [Codex CLI interactive run](codex-interactive-2026-09-24.md), [Pi real-model run](pi-generated-gtk-real-model-2026-09-24.md), [Claude/GLM native saves](claude-glm-2026-09-25.md), and [Claude lifecycle probe](claude-lifecycle-2026-09-24.md).
- Official host documentation: [Claude MCP elicitation](https://code.claude.com/docs/en/mcp#respond-to-mcp-elicitation-requests), [Claude permissions](https://code.claude.com/docs/en/permissions), [Claude elicitation hooks](https://code.claude.com/docs/en/hooks#elicitation), [MCP elicitation specification](https://modelcontextprotocol.io/specification/2025-11-25/client/elicitation), and [Pi TUI](https://pi.dev/docs/latest/tui).

## App inventory

The pinned macOS runtime's `@oai/sky/.../targets/mac/list_apps.js` maps native app records to `id`, `displayName`, `isRunning`, and optional `lastUsedDate` and `useCount`; `targets/mac/client.d.ts` declares those latter fields optional. CUA `get_apps.js` passes macOS records through, so `getState().apps` retains them (`@oai/cua/.../get_state.d.ts`). These are local app-inventory fields, not Codex account or task history. Linux's `get_apps.js` maps app names and windows to `id`, `displayName`, `isRunning`, and `windows`, with no usage fields. Windows helper parsing can preserve usage fields if returned, but this pinned source does not establish that Windows populates them. `getState()` includes browser-provider tabs; source availability does not prove live population or parity.
