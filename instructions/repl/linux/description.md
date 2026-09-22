Control Linux X11 applications through the initialized cua API. Prefer a task-specific connector or API when available.

On the first call, or after js_reset, execute exactly one entrypoint: `await cua.getState()`, `await cua.listWindows()`, or `let app = await cua.getApp({ windowId: 123 })` when that exact ID is already known. Read the returned documentation and state before continuing. Use only the documented API.
