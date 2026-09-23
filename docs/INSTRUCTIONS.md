# Original instruction delivery

The selected official application supplies the full original Linux native and Chrome instructions. LCU's release contains only its own small wrapper skill. During setup, LCU reads original files from the selected app and writes byte-identical references under the target account's local data directory before MCP registration. The agent skill installer copies those local references into the agent's skill location. They stay on the installation machine and must not be included in source archives, release assets, CI uploads, public images or portable exports.

Original sources in app 26.915.31945 include:

- resources/cua_node/lib/node_modules/@oai/cua/docs: CUA guide, native APIs, confirmations and alternate-mode documents.
- resources/cua_node/lib/node_modules/@oai/sky/docs: Linux desktop skill and native API.
- resources/cua_node/lib/node_modules/@oai/cua-repl/instructions: Linux first-call, reset, output and startup instructions.
- resources/cua_node/lib/node_modules/@oai/browser-desktop/environment-docs/codex-app: browser document graph, API declarations and Chrome capability-specific guidance.
- resources/plugins/openai-bundled/plugins/chrome/docs and skills/control-chrome: original Chrome provider docs and its separate plugin-mode skill.

The wrapper identifies the unified CUA entrypoint used by LCU. The original Chrome plugin skill documents a separate Node REPL bootstrap mode, so its bytes remain available but its bootstrap command is not substituted for LCU's already initialized CUA client. Original dynamic tool descriptions, first-call and post-reset instructions, browser capability filtering and confirmation policy still come from the installed provider. After context compaction, agents call the original rewriteDocumentation entrypoint and read the returned guidance.

A complete pre-call check must inspect the generated skill before any computer-use call, compare every generated original file to the selected app source byte for byte, and verify Linux and Chrome documents and links resolve. The old [instruction lock](../scripts/instructions.lock.json) records 195 original resources and 385 historical reference copies from the prior full-bundle candidate. That ledger is a completeness baseline, not release payload. The new generated set is the applicable Linux native and Chrome subset; shared original cross-platform source files may still be present where the original documentation links to them.

The old checked-in `instructions/` and `skills/lcu/references/` trees have been removed from the working tree. The selected app now supplies their applicable Linux and Chrome content during setup. The full-copy commit remains reachable from the remote `fix/full-linux-parity` branch; a direct-main push must use a clean history and no new release or source archive may carry those copies.
