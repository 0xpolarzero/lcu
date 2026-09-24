---
name: lcu
description: Control Linux desktop windows through the original Codex computer-use runtime.
---

Use LCU's `js` and `js_reset` tools. JavaScript state persists between calls.

Before the first call, read the complete original Linux computer-use guide at [references/upstream/cua/docs/tinysky-alt-core-cua-repl.md](references/upstream/cua/docs/tinysky-alt-core-cua-repl.md), the Linux launcher description at [references/upstream/cua-repl/instructions/linux/description.md](references/upstream/cua-repl/instructions/linux/description.md), and the native Linux guide at [references/upstream/sky/linux/SKILL.md](references/upstream/sky/linux/SKILL.md). LCU uses the unified original `cua` entrypoints and the capability-specific guidance returned by its runtime.

On first use or after reset, make one documented entrypoint call by itself, normally `await cua.getState()`. Do not combine it with other API calls, waits, or snapshots. Read the returned tool descriptions, policies, and inventory before continuing. After context compaction, call `await cua.rewriteDocumentation()` by itself and reread the returned guidance.

Use the original `cua` entrypoints and only capabilities shown by the connected provider and effective policy. For native Linux windows, target an exact observed window ID.

This skill's references are generated from the selected installed Linux application during setup. If they are missing, run `lcu setup` on the Linux machine that hosts the agent.
