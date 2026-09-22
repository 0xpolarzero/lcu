---
name: lcu
description: Read and operate Linux desktop windows using the LCU MCP computer-use tools. Use for tasks that require GUI interaction on the connected Linux machine.
---

Use LCU's `js` tool. On first use or after `js_reset`, run only `await cua.getState()` or `await cua.listWindows()`. Read the returned API documentation before continuing.

Select the intended window with `await cua.getApp({ windowId: id })`, using its exact observed ID and title. Follow the runtime's Linux instructions, including fresh observations after actions. After context compaction, run `await cua.rewriteDocumentation()`.

If the tool is missing, connect the exported MCP configuration or run `lcu setup` for the selected agent. A connected X11 desktop must already exist; installing LCU does not start one. Do not substitute another desktop automation engine.
