# Original instruction delivery

The selected official application supplies the full original platform-native and Chrome instructions. LCU's release contains only its own small wrapper skill. Default setup copies the original platform-native references; `lcu setup --chrome` also copies original browser-desktop and Chrome plugin references and registers `lcu --chrome`. The agent skill installer copies those local references into the agent's skill location. They stay on the installation machine and must not be included in source archives, release assets, CI uploads, public images or portable exports.

Linux uses the `linux` instruction and Sky skill branches. macOS uses `macos` from `Contents/Resources` in its signed local app. The original launcher selects its dynamic instructions through `process.platform` and `CUA_REPL_ENABLED_SURFACES`; LCU does not ask the model to choose an operating system or rewrite the original guide. Default `lcu` selects the computer surface, while `lcu --chrome` selects browser and computer. The original shared core guide can still mention browser methods in computer-only mode, but those methods are absent from the active API. Pi receives the same upstream tool descriptions, schemas and initialization instructions through [its adapter](ADAPTERS.md).

Original sources in Linux app 26.915.31945 include:

- resources/cua_node/lib/node_modules/@oai/cua/docs: CUA guide, native APIs, confirmations and alternate-mode documents.
- resources/cua_node/lib/node_modules/@oai/sky/docs: Linux desktop skill and native API.
- resources/cua_node/lib/node_modules/@oai/cua-repl/instructions: Linux first-call, reset, output and startup instructions.
- resources/cua_node/lib/node_modules/@oai/browser-desktop/environment-docs/codex-app: browser document graph, API declarations and Chrome capability-specific guidance.
- resources/plugins/openai-bundled/plugins/chrome/docs and skills/control-chrome: original Chrome provider docs and its separate plugin-mode skill.

The wrapper identifies the unified CUA entrypoint used by LCU. In Chrome-opt-in setup, the original Chrome plugin skill documents a separate Node REPL bootstrap mode, so its bytes are available for reference but its bootstrap command is not substituted for LCU's already initialized CUA client. Original dynamic tool descriptions, first-call and post-reset instructions, browser capability filtering and confirmation policy still come from the installed provider. After context compaction, agents call the original rewriteDocumentation entrypoint and read the returned guidance.

A complete pre-call check must inspect the generated skill before any computer-use call, compare every generated original file to the selected app source byte for byte, and verify the selected platform references resolve. For Chrome-opt-in setups it must also verify Chrome references. The old [instruction lock](../scripts/instructions.lock.json) records 195 original resources and 385 historical reference copies from the prior full-bundle candidate. That ledger is a completeness baseline, not release payload. The generated set contains the applicable platform-native subset and adds the browser subset only on opt-in; shared original cross-platform source files may still be present where the original documentation links to them.

The old checked-in `instructions/` and `skills/lcu/references/` trees have been removed from the working tree. The selected app now supplies their applicable platform and Chrome content during setup. The full-copy commit is absent from the new local main lineage, and its remote feature branch was deleted. No new release or source archive may carry those copies.
