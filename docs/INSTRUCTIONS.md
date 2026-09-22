# Instruction fidelity

LCU retains the complete original instruction resources from the pinned OpenAI Linux package `26.915.31945`, runtime `0.0.16/20260915001755-492f19756c31`. It does not condense or rewrite the upstream guides. The runtime's own files remain in their original locations; the skill also carries byte-identical copies that an agent can read before making its first tool call.

## Source inventory

[`scripts/instructions.lock.json`](../scripts/instructions.lock.json) records every file in nine complete instruction roots, including its original SHA-256 and all local copies. The 195 source resources are identical across the ARM64 and x86-64 packages. They produce 385 byte-identical copies under `instructions/` and `skills/lcu/references/`; no ledger entry has an edit.

| Original source root | Included guidance |
| --- | --- |
| `cua_node/lib/node_modules/@oai/cua/docs` | Default and alternate core guides, confirmations, and alternate browser APIs |
| `cua_node/lib/node_modules/@oai/cua-repl/instructions` | All platform/tool descriptions, browser environments, disabled-surface text, banner, output, reset, and server guidance |
| `cua_node/lib/node_modules/@oai/sky/docs` | Native API guides and original platform skills, including the complete Linux desktop skill |
| `cua_node/lib/node_modules/@oai/browser-desktop/environment-docs` | Codex-app, cloud, orbit, and training API/document manifests and every referenced guide |
| `cua_node/lib/node_modules/@oai/cua/dist/lib/js/oai_js_browser/dist/skill/references` | Embedded browser-runtime references and capability/document manifests |
| `plugins/openai-bundled/plugins/browser/docs` | Original in-app browser plugin documentation |
| `plugins/openai-bundled/plugins/chrome/docs` | Original external-browser plugin documentation |
| `plugins/openai-bundled/plugins/browser/skills` | Original in-app browser skill |
| `plugins/openai-bundled/plugins/chrome/skills` | Original Chrome skill |

The [complete runtime and host inventory](INVENTORY.md) separately covers every implementation file, public package export, API declaration, configuration identifier, plugin artifact, and dynamic-document graph. Shared packages retain their inactive platform branches and documentation as shipped; their presence does not make a non-Linux API available on Linux.

## Instruction producers

The original `@oai/cua-repl` launcher composes its `js` description from the selected platform's common, browser/computer or disabled-surface, and output guidance. It also supplies the original server instructions, code field description, reset description, and initialization banner.

The banner loads `@oai/cua/tinyskyAlt`. Its instruction producer selects `core-cua-repl` by default, or the guide selected by `TINYSKY_ALT_INITIALIZE_DOCS` when the host exposes that setting. Both original core guides are retained. `cua.initialize()` exists as an alias of `cua.getState()`; it was incorrectly described as absent in the v0.2.1 audit.

The first entrypoint call emits the selected core guide and applicable policy before inventory/action output. The default confirmation policy remains unchanged; the original implementation accepts valid host policy metadata under `openai/confirmation_policies`. Reset and `cua.rewriteDocumentation()` retain the original caching, replay, and request-metadata behavior.

Browser selection additionally supplies the original alternate-API guidance and that browser's generated documentation. Its API and document manifests filter guidance according to browser type, available APIs, browser/tab capabilities, environment, and the original exclusion settings. All source manifests and referenced guides are retained; the agent must use the effective documentation returned for its selected browser rather than assume every cataloged capability is connected.

## Standalone integration notes

The [LCU skill wrapper](../skills/lcu/SKILL.md) contains the only additional integration guidance. It maps the upstream `cua_repl` name to the standalone `js`/`js_reset` tools, links full original guides, and records these implementation-backed differences without altering the originals:

- Native Linux `cua.getApp` requires an observed `{ windowId }`. The shipped Linux tool-description example uses a string incorrectly; the original full core guide and implementation both specify the window-ID form.
- Within this initialized REPL, the original full-desktop client is already available at `cua.computer`. The standalone Sky examples import `sky`; binding `const sky = cua.computer` uses the existing original client and trusted service.
- Legacy browser plugin bootstrap instructions apply to their own plugin modes. The unified LCU entrypoint is already initialized. Browser capabilities that depend on the Codex application, such as its in-app browser, require that host; copying their instructions is not a claim that their host exists.

Original policy files are available as references, but host-provided policy metadata remains authoritative for the runtime's emitted policy. No additional policy or task-success guarantee is introduced by the wrapper.

## Verification

```sh
# Verify every checked-in upstream reference against its recorded original hash.
python3 scripts/project_instructions.py

# Also enumerate all original resource roots and reject omissions/additions/drift.
python3 scripts/project_instructions.py --upstream-modules /absolute/resources/cua_node/lib/node_modules

# Recreate reference copies from a separately verified original extraction.
python3 scripts/project_instructions.py --upstream-modules /absolute/resources/cua_node/lib/node_modules --write
```

Build verification rejects changed bytes, missing resources, unclassified additions inside any resource root, and attempted instruction rewrites. Runtime inventory checks also reject changes anywhere outside those roots. This proves source preservation and reproducible delivery inputs. Equal agent reliability additionally depends on the original host configuration, full agent-visible output, connected backends, policies, model behavior, and differential tests; file equality alone does not establish it.

## Earlier releases

Versions through v0.2.0 used a hand-written core summary. Version v0.2.1 restored a reviewed Linux-native projection but excluded browser providers and selected instruction modes. The complete-copy design supersedes that selected-subset approach. Earlier successful fixture tests do not establish completeness of the omitted interfaces.
