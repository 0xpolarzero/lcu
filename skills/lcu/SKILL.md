---
name: lcu
description: Use a Linux desktop through LCU. Read windows, click controls, type text, and take screenshots when a task needs the GUI on the connected Linux machine.
---

Use LCU's `js` tool. On first use or after `js_reset`, run only `await cua.getState()` or `await cua.listWindows()`. Read the returned API documentation before continuing.

That first call reads the window inventory and returns the full instructions; it does not send clicks or keystrokes. Do not add other API calls, waits, or snapshots to that invocation.

The full [computer-use instructions and API](references/api.md) are also available here before making any tool call. They retain the pinned upstream wording with explicit Linux and standalone-tool corrections. The runtime supplies the upstream confirmation policy, including any policy override supplied by the host.

For desktop-wide input, pointer movement, structured accessibility trees, or a drag that must stay held during an observation, read the [upstream Linux desktop reference](references/linux-desktop.md) before using those methods. Its `sky` binding is the original client already available as `cua.computer`.

Select the intended window with `await cua.getApp({ windowId: id })`, using its exact observed ID and title. Follow the runtime's Linux instructions, including fresh observations after actions. After context compaction, run `await cua.rewriteDocumentation()`.

If the tool is missing, connect the exported MCP configuration or run `lcu setup` for the selected agent. A connected X11 desktop must already exist; installing LCU does not start one. Do not substitute another desktop automation engine.
