# Claude Code and GLM computer-use probe, 2026-09-25

## macOS approval probe

A guarded normal Claude Code 2.1.204 session used an isolated configuration and a process-environment Z.ai endpoint (`https://api.z.ai/api/anthropic`). The real `GLM-5.3-Flash` model replied `READY`. This was a real-model session, not a scripted-provider fixture.

At test time, the selected signed ChatGPT app was 26.917.71314, newer than the LCU-pinned 26.917.62051. LCU rejected it before exposing tools. Reinstalling the frozen archive against the preserved, code-signature-verified 26.917.62051 app restored the LCU MCP connection. Claude's `/mcp` server inventory showed four original tools; the installed exact deny rules kept the two host-only tools out of the model-visible set, as established by the prior scripted-provider check.

The model called original `mcp__lcu__js` to inspect TextEdit. Claude displayed the original elicitation prompt, `Allow Computer Use to use "TextEdit"?`, with Accept and Decline choices. Decline returned `Computer Use was not approved to use TextEdit` and blocked the tool action. On a retry, accepting reached the original LCU server, which returned `-10005 timeoutReached` before a native action was confirmed. The agent observed the acceptance; the model's later claim that it received no answer was inaccurate and is not evidence of the UI result. No native save is claimed from this macOS attempt.

The original native helper was not stopped, replaced, or modified. The existing `SkyComputerUseService` appeared to use the original shared group-container socket and LaunchServices fallback, so a conflict is plausible but unproven. The timeout's cause remains unresolved. This test establishes that Claude Code's built-in MCP elicitation UI can render and return the approval decision; it does not establish successful native execution on this Mac after the app update.

Anthropic's [Claude Code MCP documentation](https://code.claude.com/docs/en/mcp#respond-to-mcp-elicitation-requests) says form and URL elicitation dialogs appear automatically without user-side configuration. The implementation needed to deliver this existing approval UI was already present; no replacement approval implementation was added.

## Linux native GTK probe

The backend was a disposable network-disabled Linux ARM64 container named `lcu-claude-glm-native`, using LCU 0.3.0 from the final `00f47db` ARM64 archive (SHA-256 `0dda40b7f3e975e4a3bba4c242f4ed99486ead681b9f5b2e3045be37b1ff0cb9`) and the pinned official ChatGPT Linux 26.915.31945/CUA 0.0.16 runtime. It ran Xvfb `:99` and the generated `LCU Target` and `LCU Other` GTK windows. Claude Code 2.1.204 ran on the host with an isolated configuration; its project MCP command relayed through `docker exec` to the original LCU runtime, and the isolated project contained the platform-correct generated Linux skill. A real Z.ai GLM 5.3 Flash session connected to the MCP server and showed `lcu connected · 4 tools`.

No model-directed native Save or independent GTK oracle pass occurred in this run.

A paired direct-SDK diagnostic used the same installed adapter, command, `getState` request, session/turn shape, MCP capabilities, X11 display, D-Bus address, and GTK environment, changing only the container UID. The `ubuntu` process returned `apps: []` with an X11 `Operation not permitted` error; the root process's `getState` did not return that X11 error. This is a bounded UID comparison and does not establish why the runtime's sandboxed access differs. No sandbox was disabled or changed.

Claude's real-model original `js` call against the Linux GTK backend returned X11 `Operation not permitted` under both the ordinary `ubuntu` UID and a retry whose MCP worker process tree was verified as root. In the controlled direct-SDK comparison, root's `getState` did not return the X11 error that appeared under `ubuntu`, but that result did not carry over to Claude's actual worker chain. The cause remains unresolved. The GTK Target and Other windows were present, but Claude made no UI edit or save. The independent `Target.txt` and `Other.txt` oracle files were both absent. The isolated Claude shell exited after its provider environment variables were unset, temporary state was removed, and the disposable container was stopped and removed. No model-driven desktop save through Claude Code passed.

## Known lifecycle boundary

The elicitation result does not close the separate per-turn lifecycle gap. Claude Code's current LCU registration still does not send original `turn_ended` on normal completion or interruption; see the [lifecycle probe](claude-lifecycle-2026-09-24.md).
