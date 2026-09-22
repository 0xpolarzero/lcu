# Instruction fidelity

## Source and scope

The source is OpenAI's pinned Linux package `26.915.31945`, runtime `0.0.16/20260915001755-492f19756c31`. The [ARM64 package](https://persistent.oaistatic.com/codex-app-prod/linux/deb/pool/main/c/chatgpt/chatgpt_26.915.31945_arm64.deb) and [x86-64 package](https://persistent.oaistatic.com/codex-app-prod/linux/deb/pool/main/c/chatgpt/chatgpt_26.915.31945_amd64.deb) are verified against `runtime.lock.json`. All 12 instruction inputs have identical bytes in both packages.

Versions through v0.2.0 replaced the core guide with a hand-written summary. That omitted applicable workflow rules, including avoiding repeated observations, preferring already-visible results, stopping after visible completion, and persistence after ineffective actions. v0.2.1 replaces the summary with a reproducible projection of the original text. It also restores the upstream Linux full-desktop skill as a reference.

`@oai/cua-repl` selects `core-cua-repl`, not `core-node-repl`. The latter documents a different host entrypoint, including `cua.initialize()`, which is absent from this runtime's selected interface; it is not substituted for the active guide. Other-platform instructions and dedicated browser-provider APIs are excluded. Browser application windows remain usable through Linux desktop APIs. The original confirmation policy is copied unchanged, and the original runtime's host-policy override behavior is retained.

The Linux full-desktop reference retains the upstream skill body. Its only executable change binds `sky` to the original initialized client at `cua.computer`, instead of importing a second client. The standalone skill wrapper supplies registration and routes to these references; it does not replace their workflow rules.

This establishes traceable instruction fidelity to the selected files in this pinned package. It does not claim access to every Codex host prompt, parity with later packages, or equal agent task-success rates. The docs and runtime remain subject to their upstream terms, as described in [PROVENANCE.md](PROVENANCE.md).

## What the agent receives

1. The registered LCU skill exposes full local references before any tool call.
2. MCP initialization and tool discovery provide the upstream server, first-call, output, and reset instructions, with the edits below.
3. The first documented call, `await cua.getState()` or `await cua.listWindows()`, initializes the original REPL, emits the full API guide plus the applicable confirmation policy, and reads inventory. It does not click, type, or launch an application. The agent reads that result before continuing.
4. Reset and `cua.rewriteDocumentation()` use the original delivery and replay behavior.

The integration suite compares the complete tool description, initial API text, default policy, reset output, and replay output with the reviewed files. It also exercises the full-desktop reference's client binding, structured accessibility, and screenshot example against independent Linux GUI fixtures. These are delivery and execution checks, not a claim that every agent model follows every instruction.

## Reproduction and drift checks

[`scripts/instructions.lock.json`](../scripts/instructions.lock.json) records source paths, SHA-256 hashes, exact original line spans, replacements, reasons, and output hashes. Lines outside those edits survive byte-for-byte, in their original order. The build validates the extracted official text, reproduces the edits, and compares every packaged and skill-reference copy. Missing files, upstream drift, overlapping edits, unexplained edits, changed output, and manually condensed copies fail closed.

```sh
# Check every committed projection and reference against the reviewed hashes.
python3 scripts/project_instructions.py

# Reproduce against an extracted, checksum-verified official runtime.
python3 scripts/project_instructions.py --upstream-modules /absolute/runtime/lib/node_modules

# Regenerate after reviewing any deliberate changes to the ledger.
python3 scripts/project_instructions.py --upstream-modules /absolute/runtime/lib/node_modules --write
```

## Complete edit inventory

Source paths below are relative to `lib/node_modules` in the official runtime. Line numbers refer to the pinned original, not the generated output. The exact replacement text is in the ledger.

### `@oai/cua/docs/tinysky-alt-core-cua-repl.md`

Outputs: `instructions/api/tinysky-alt-core-cua-repl.md`, `skills/lcu/references/api.md`.

| Original lines | Reason |
| --- | --- |
| 5 | The standalone MCP exposes js; cua_repl is the upstream host namespace. |
| 6 | Retain the tool restriction and user exception; remove examples specific to macOS. |
| 8 | Use the standalone tool name. |
| 9 | The dedicated browser provider is disabled. |
| 18 | The Linux implementation rejects non-text paste formats. |
| 20–24 | SelectTextOptions applies to selectText, which always throws on Linux. |
| 26 | SelectionType applies to selectText, which always throws on Linux. |
| 35 | Linux rejects page counts and accepts a positive pixel distance or its native default. |
| 36–37 | selectText and setValue always throw on Linux; retain their explicit warning in Notes. |
| 55 | Linux rejects page counts. |
| 62–99 | Dedicated browser and tab provider types are outside this computer-only runtime. |
| 102 | The browser inventory is empty when the dedicated provider is disabled. |
| 103 | Only the native app inventory is enabled. |
| 106–123 | Dedicated browser options and Tab methods are outside this computer-only runtime. |
| 127 | Only the Linux platform is retained. |
| 128 | launch_app is present in the pinned Linux client. |
| 131 | Linux getApp requires an observed window ID; strings throw. |
| 133 | listWindows is present on Linux. |
| 134 | Document the existing runtime method prescribed by the upstream first-use tool description. |
| 135–149 | Dedicated browser-provider methods are disabled. |
| 155 | Remove macOS target selection and Windows applicability; retain exact-window selection and multi-window guidance. |
| 157 | Retain Linux inventory and launch behavior; remove Windows applicability. |
| 159 | Remove the Windows-only activation and screenshot-coordinate mapping behavior. |
| 164 | Linux always returns full trees; retain the requirement to refresh indices after a screenshot-only observation. |
| 165 | Retain all Linux accessibility-source guidance. |
| 169 | Remove dedicated tab-provider calls; retain automatic app observation. |
| 177–182 | Use native app text/key signatures and pixel scrolling; omit methods that always throw on Linux. |
| 191 | Remove disabled browser-provider output rules; preserve automatic output and first-use documentation behavior. |
| 192 | Remove Windows-only screenshot emission and error behavior. |
| 196 | This element-first input convention applies only to dedicated browser tabs. |
| 198 | Remove macOS/browser clipboard behavior and formatted paste unsupported on Linux; retain native text input and multiline advice. |
| 199 | Remove macOS page counts and Windows coordinate-only scrolling; retain every Linux rule. |
| 200 | Both unsupported-method warnings remain for Linux. |
| 203 | selectText always throws on Linux; its operational instructions apply to other platforms. |
| 205 | This app-name resolution and implicit launch behavior is macOS-only. |

### `@oai/cua-repl/instructions/banner.js`

Outputs: `instructions/repl/banner.js`.

Copied unchanged.

### `@oai/cua-repl/instructions/browser-disabled.md`

Outputs: `instructions/repl/browser-disabled.md`.

Copied unchanged.

### `@oai/cua-repl/instructions/computer-disabled.md`

Outputs: `instructions/repl/computer-disabled.md`.

Copied unchanged.

### `@oai/cua-repl/instructions/server.md`

Outputs: `instructions/repl/server.md`.

Copied unchanged.

### `@oai/cua-repl/instructions/code.md`

Outputs: `instructions/repl/code.md`.

Copied unchanged.

### `@oai/cua-repl/instructions/linux/output.md`

Outputs: `instructions/repl/linux/output.md`.

Copied unchanged.

### `@oai/cua-repl/instructions/reset.md`

Outputs: `instructions/repl/reset.md`.

| Original lines | Reason |
| --- | --- |
| 1 | Use the standalone MCP tool name; retain reset semantics verbatim. |

### `@oai/cua-repl/instructions/linux/description.md`

Outputs: `instructions/repl/linux/description.md`.

| Original lines | Reason |
| --- | --- |
| 4 | Remove dedicated browser/tab selection; retain the requirement to read the first result before further calls. |
| 7 | Only the native computer surface is enabled. |

### `@oai/cua-repl/instructions/linux/computer.md`

Outputs: `instructions/repl/linux/computer.md`.

| Original lines | Reason |
| --- | --- |
| 1 | Fix the shipped Linux entrypoint that incorrectly accepts names/paths; the Linux branch requires { windowId }. |
| 4 | Use an observed window ID as required by the Linux implementation. |

### `@oai/cua/docs/tinysky-alt-confirmations.md`

Outputs: `instructions/api/tinysky-alt-confirmations.md`.

Copied unchanged.

### `@oai/sky/docs/skills/oai_sky_lib/linux/SKILL.md`

Outputs: `skills/lcu/references/linux-desktop.md`.

| Original lines | Reason |
| --- | --- |
| 1–5 | Store the upstream Linux skill body as a reference under the registered lcu skill. |
| 33 | The original Linux client is already initialized behind the trusted service at cua.computer; no new client or import is needed. |

