# Standalone integration adaptations

LCU launches the original @oai/cua-repl server, original Sky/native services and original Chrome provider from one selected official Linux app generation. It adds only the host integration needed outside the ChatGPT desktop application.

| Adaptation | LCU behavior | Boundary |
| --- | --- | --- |
| App selection | A verified private versioned package payload is selected through each LCU release's app link and installation descriptor. | No OpenAI files are rewritten or placed in the LCU archive. |
| Executable paths | The child environment points to the selected app's Node, node_repl, Codex CLI, module and plugin roots. | Explicit caller policy and sandbox settings survive. |
| CODEX_HOME | An explicit value is passed verbatim; otherwise Linux HOME is joined with .codex as the pinned Node host does. Empty trust entries are omitted. | Only the launched child environment changes; no user Codex configuration is edited. |
| Generic MCP ownership | A generated connection ID supplies routing identity only when a host supplies no request metadata. | It is not an account, model identity, approval, or real turn event. Per-call metadata takes precedence. |
| Desktop session | lcu-session selects one existing same-user XFCE X11 session, or direct mode uses the caller's GUI environment. | LCU does not create a desktop or VM. |
| Chrome native host | LCU copies the original plugin from the selected app into the target account's writable data directory because its original installer writes beside its executable, runs that installer, then points the account's manifest at LCU's small relay. The relay changes only a fresh extension's `agentRequestHeaderEnabled: false` reply to `true`. | The original provider, host and extension still perform browser actions. LCU locally enables the website-visible `x-browser-agent` label and skips the Codex account feature-gate lookup on this path. Original MCP site approval remains active. The account-level manifest also affects other apps using that extension; the extension persists the header state in its profile. |
| Agent delivery | Setup materializes original applicable instructions byte-identically in the target account and registers the fixed original MCP policy and lifecycle hooks. | Portable exports contain bootstrap metadata, not OpenAI documents. Generic hosts must honor the exported contract. |

The fixed app package's post-install script would register an apt source and apply an AppArmor profile for /usr/lib/chatgpt/ChatGPT, its Electron UI. LCU does not run that script or launch that UI. The installed ARM64 thin archive passed a native fixture and a no-sign-in Chrome action in an Ubuntu 24.04.5 VM with AppArmor active; see the [verification record](verification/installed-app-2026-09-23.md). Native x86-64 host behavior remains unverified.

The old embedded-browser host, extraction script, protocol handler and renderer shims have been removed from the active source. The active launcher returns migration errors for their CLI flags. The prior full-copy commit remains on a remote feature branch and must not be included in a direct-main push.
