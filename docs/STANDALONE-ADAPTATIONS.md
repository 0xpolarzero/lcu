# Standalone adaptations

The baseline is package `26.915.31945` on each Linux architecture. The entire
`/usr/lib/chatgpt` tree is retained without modifying its files. No upstream
instruction resource is edited. This ledger describes LCU-owned integration
around those original files, including differences that still require testing.

| Adaptation | Reason and implementation | Parity consequence |
| --- | --- | --- |
| Installation paths | `runtime/`, `host/bin/`, and `host/plugins/` are aliases into the complete bundled application. The launcher supplies bundled Node/REPL/module paths. | Original code, exports, dependencies and resources remain intact; relocation needs release tests. |
| Enabled surfaces | The original launcher receives `browser,computer` by default. Caller overrides remain authoritative. | Deliberately enables shipped Linux functionality independently of the app's product-availability gates. |
| Namespace | Agent registration uses `lcu` instead of `cua_repl`; the original tool schemas remain unchanged. | Original hook references use the same namespace substitution. |
| Before-call guidance | The separate LCU skill links full, unchanged original guides and records the native `{windowId}` entrypoint and existing `cua.computer` binding. | Original misleading Linux string-selection example remains untouched in its source. Wrapper notes are distinguishable from upstream text. |
| Generic-client identity | If absent, the launcher provides a UUID identifying the actual MCP connection and its fallback connection turn. Real request metadata takes precedence. | This does not create real agent-turn boundaries, approvals, model identity, authentication, or lifecycle hooks. Generic hosts must supply those. |
| Telemetry default | `NODE_REPL_DISABLE_ANALYTICS=1` unless the caller sets it. | Documented standalone default, not an upstream source change. |
| Codex tool delivery | Registration imports the original enabled-tools list, routing exclusions, startup timeout and JavaScript output budget. | Other clients must implement the exported host contract. A skill plus unrestricted MCP registration alone is insufficient. |
| Codex lifecycle registration | The original Stop, Interrupt and SubagentStop records are installed through the original CLI configuration writer. Trust applies only to their exact original-content hashes. | Project definitions stay project-scoped; native Codex requires path-specific user trust records. Six cases, including overlapping scopes, passed original ARM64 execution; final candidate gates remain. |
| Chrome native-host installation | Copies the complete original Chrome plugin into private account storage, then runs its unchanged installer. | The sealed release stays immutable. The official extension, browser, identity service and authorization remain dependencies. |
| IAB entrypoint | `--with-browser-host` owns the original host alongside MCP; `browser serve --session-id ID` runs it explicitly. Default MCP startup remains independent of Electron. | Original runtime can initialize without an available IAB provider. Explicit host provisioning prevents an Electron failure from disabling native control. |
| Original IAB exports | Build-time extraction exposes original declaration closures from `app.asar`; `host/iab/derivation.json` records source/output hashes and original byte spans. The unchanged full archive remains bundled. | The extractor redirects only module resolution/bootstrap exports; it avoids launching the full Codex desktop app. Extraction is not behavioral proof. |
| IAB shell | LCU supplies local owner windows, IPC and session registration to the original provider, registry, browser host, network policy and renderer controllers. | Missing product services are tracked in the host parity report. They are blockers, not excluded capabilities. |
| OAuth startup | Mount the original pending/callback hooks before accepting session operations and acknowledge readiness only after their subscription exists. | Empty and valid no-state redirect registrations must return the original null outcome without timing out. ARM64 focused provider regression passed; immutable archive gates remain. |
| Browser layer placement | The standalone panel has no artificial stacking priority above the original body-level webview host. The original host controls its frame and overlay layers. | A native-pointer fixture checks the actual WEBVIEW hit target before Allow/Block; both clipboard outcomes and original early-click guard pass on ARM64 development code. Fresh archive gates remain. |
| Annotation screenshot diagnostics | The original `captureBrowserScreenshot` catches capture errors, calls `reportNonFatal(error, {kind: 'browser-sidebar-comment-screenshot'})`, and returns. LCU reports that callback as `lcuHost:nonfatal` and logs it; `lcuHost:error` still fails shutdown. The fixture waits for the original submit request to settle before reporting the saved body and guest marker. | A saved comment can survive a screenshot failure. The fixture wait proves the original async submit finished, not that screenshot bytes were captured. |
| Browser shell commands | The owner window forwards the original app-shell shortcut state, resolves a single visibly presented original browser route, mounts the original Find surface, and binds native menu accelerators from the pinned original menu expression and keymap. Menu actions call original focused-page methods; Find queries use original `runPageCommand`. | The installed-release ARM64 native-input fixture checks independent page URLs, load count, visible Find count and tab removal. Final release gates must repeat it on both architectures. |
| Session routing | The MCP bridge observes actual request session metadata, registers that exact owner, waits for acknowledgment, and forwards the original line unchanged. | No wildcard ownership. Closed-owner events invalidate the bridge's cache. Needs multi-session and recovery tests. |
| Linux protocol delivery | An opt-in desktop handler targets one explicitly selected live session through a same-user private socket and the original `dk` queue. Default association changes require explicit selection. | Original queue acceptance is distinct from authenticated OAuth completion. Occupied socket paths fail closed, cleanup checks the bound inode, and client limits/deadlines bound transport lifetime. Both architecture fixtures exercised GIO and owner isolation; fresh archives remain. |
| Browser profile | The native Owl launch receives an LCU-owned `--user-data-dir`, keyed by initial session identity; `LCU_BROWSER_PROFILE` can explicitly select a retained profile. | Never implicitly uses the user's Codex profile. A random fallback identity does not preserve browser storage across reconnections. Simultaneous hosts must not share one profile. |
| Network requirements | A strict-config original CLI connection supplies actual `configRequirements/read` and version. Account updates refresh policy; connection loss invalidates it. | No fabricated unrestricted requirement or sandbox bypass. Parent-agent notifications and authenticated workspace services need explicit host integration. |
| MCP backpressure | Nonblocking forwarding keeps policy monitoring active when the original child stops reading or is closing. | Local process tests cover this transport failure; they do not prove full Electron policy behavior. |
| Fixed host environment | Original `nne` timeout (1000 ms), admitted unified-path Tinysky flag, original app version and validated build flavor are supplied. Original Eie/Die use-case strings are copied unchanged for selected browser providers. | Explicit caller overrides remain. The original unified launcher overrides its tool guidance; use-case flags affect bare Node REPL guidance. Model checks and backend availability still require actual host decisions. |
| Original account services | Original HB and D$ methods use a private request/response bridge to real `getAuthStatus`, `account/read` and `configRequirements/read`. | Tokens are not printed or fabricated. Original account-backed behavior needs an authenticated test environment. Unexpected approval requests are not automatically answered. |
| Original desktop settings | Original vD/OD read and persist desktop preferences through the actual CLI. The bridge permits desktop settings writes, without extending it to approval or sandbox configuration writes. Shutdown continues servicing RPC until original settings flush. | Fixture TOML outcomes prove the tested keys persisted and unrelated policy stayed intact. Requirements refresh also rehydrates settings, an additional standalone timing choice. |
| Parent connection seam | `BrowserHost(..., app_server_connection=connection)` can use the caller's actual initialized RPC adapter and its `subscribe_notifications()` subscription. The caller owns the connection; the browser host owns only its subscription. The default remains a separate bundled CLI. | The adapter routes replies by request ID and gives each subscription its own notification queue. A real pipe test proves browser polling preserves a concurrent caller's reply. `AppServer(request_handler=...)` delegates incoming RPCs to the caller and requires a response with the original request ID; without one it returns an explicit unsupported error. No acceptance policy is synthesized. Supplying the actual parent connection remains required for parent event parity; no parent event stream is invented. |
| Codex-home code trust | The original app additionally trusts its selected Codex home. LCU still trusts its existing bundled module/plugin roots and explicit caller roots. | Automatic approval review rejected broadening the default trust domain. This remains an approval-blocked parity difference. |

The [host inventory](HOST-INVENTORY.md), [browser status](BROWSER-HOST-PARITY.md),
[external dependencies](BROWSER-DEPENDENCIES.md) and [verification](VERIFICATION.md)
separate retained code, implemented adapters, executed behavior and outstanding
requirements. Do not convert this ledger into a full-parity claim.

Annotation source: the original bundled `.vite/build/main-DUHZj4_w.js`
`eGe.captureBrowserScreenshot` and `eGe.captureSavedCommentScreenshot`, exposed
at generated `host/iab/provider.cjs:766`; the latter is awaited by
`handleOverlaySubmit`. In the frozen ARM64 release, the old fixture failed
graceful shutdown in 1/4 isolated runs after saving the body and marker. A
temporary source overlay passed 4/4 runs; a fixture-only `capturePage()` failure
logged `Original IAB host nonfatal: UnknownVizError`, retained the saved body and
marker, and exited gracefully. `tests/test_host_bridge.py` separately asserts
that a fatal host error still aborts shutdown.

The final Find adapter correction follows the original native-menu decision:
`runFocusedVisiblePageCommand` gets the first opportunity; an unhandled command
falls back to the original renderer messages `find-in-thread`,
`find-next-in-thread`, or `find-previous-in-thread`. Observed non-null renderer
focus areas are retained; an unknown area resolves to the standalone window's
single right-panel route. The fallback fixture observes the original Search
chat domain, while the normal browser workflow requires the focused Find input
and three independently present page matches. Four normal x86-64 runs and the
fallback control passed before archive verification. Earlier traces showed
initial input focus followed by the webview regaining focus; these passes do
not conclusively isolate that earlier focus change. The deep-link adapter also
preserves the original `reportNonFatal` severity, using the same logged nonfatal
bridge event as annotation reports.
