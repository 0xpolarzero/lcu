---
name: lcu
description: Control Linux desktop windows and supported browser tabs through LCU's original Codex computer-use runtime. Use when a task requires reading or interacting with the GUI on the connected Linux machine.
---

Use LCU's `js` and `js_reset` tools. The upstream guides call this interface `cua_repl`; in this standalone installation that means these LCU tools. JavaScript state persists between calls.

Before any interaction, read the complete [upstream computer-use guide](references/api.md). The [original Linux first-call description](references/repl/linux/description.md), [browser entrypoints](references/repl/linux/browser.md), and [output/recovery instructions](references/repl/linux/output.md) are available locally too. These files preserve the original text, not summaries.

On first use or after reset, make one documented entrypoint call by itself, normally `await cua.getState()`. Do not add other API calls, waits, or snapshots to that invocation. It returns the original instructions and inventory. Read that result before continuing. After context compaction, use `await cua.rewriteDocumentation()` and reread any specialized reference you still need.

The original guides cover multiple platforms and host modes. Apply their Linux branches and the capabilities of the selected browser. Two standalone integration details apply:

- For native Linux windows, use `await cua.getApp({ windowId: id })`, with the exact observed ID and title. The original Linux tool-description example incorrectly uses an app name; the implementation rejects strings. The full API guide documents the correct Linux form. Linux native `selectText` and `setValue` are unavailable; native scrolling takes `{ pixels: 500 }` or the default, as described in that guide.
- For the low-level Linux API, read the complete [original Linux desktop skill](references/linux-desktop.md) or [native API reference](references/native-api.md). In this initialized REPL, use `const sky = cua.computer;` for the original client. The upstream standalone examples import `sky` directly; creating another client is unnecessary here. All original methods, types, window targeting, clipboard guidance, and drag cleanup instructions are preserved in those references.

For browser tasks, use the original `cua.getBrowser`, `cua.getTab`, and `cua.createBrowserTab` entrypoints and read the selected browser's returned documentation. It reflects that browser's actual capabilities. Before choosing alternate browser APIs, read the [original guidance](references/other-browser-apis.md). The complete source references are available before a call:

- Default Codex browser environment: [API declarations](references/browser/codex-app/api.json), [documentation selection rules](references/browser/codex-app/documents.json), and [bootstrap troubleshooting](references/browser/codex-app/bootstrap-troubleshooting.md).
- Cloud/CDP mode: [entrypoints](references/repl/linux/browser-cloud.md), [API declarations](references/browser/cloud/api.json), and [documentation selection rules](references/browser/cloud/documents.json).
- Other original modes: [training](references/browser/training/documents.json) and [orbit](references/browser/orbit/documents.json).
- Original browser-plugin integration instructions: [Chrome](references/plugins/chrome.md) and [in-app browser](references/plugins/in-app-browser.md). Their legacy bootstrap examples belong to those plugin modes; with LCU's initialized `cua` interface, follow the unified entrypoints above. An in-app browser requires its original hosting application.

These reference catalogs retain every capability condition and linked document. Do not treat a catalog entry as evidence that its backend is connected. Follow the selected browser's discovery results and effective documentation. Do not substitute a different browser when the user requested a specific one.

The runtime delivers the [original confirmation policy](references/confirmations.md), or the applicable policy supplied by the host. The [alternate node-REPL guide](references/api-node-repl.md) is also retained for hosts selecting that original documentation mode; it does not replace the default `cua_repl` guide.

If the tools are missing, connect the exported MCP configuration or run `lcu setup` for the selected agent. A connected Linux graphical session must already exist; LCU does not start a desktop. Do not substitute another automation engine.
