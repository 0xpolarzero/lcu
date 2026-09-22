# Original implementation inventory

The build checks complete file inventories rather than a selected list of twelve guides or a tree-shaken JavaScript dependency graph. The pinned official package checksum identifies the source archive. Independent architecture inventories then identify every retained file, byte count, SHA-256, permission mode, directory, and symlink target. The runtime has zero file exclusions and no source rewrites.

## Recorded source trees

| Original source | Destination | Inventory |
| --- | --- | --- |
| `usr/lib/chatgpt/` | `host/application/` | Complete original Linux application: 4,380 file, directory, and symlink entries per architecture; zero exclusions |
| `resources/app.asar` internals | Retained inside the original archive | 15,480 leaves (15,110 packed files and 370 unpacked file references), plus 335 directories per architecture |
| `usr/lib/chatgpt/resources/cua_node/` | `runtime/` alias into `host/application/` | 2,260 files and 322 directories per architecture |
| `resources/plugins/openai-bundled/plugins/browser/` | `host/plugins/browser/` | Complete original plugin, including its implementation, dependencies, docs, skill, and assets |
| `resources/plugins/openai-bundled/plugins/chrome/` | `host/plugins/chrome/` | Complete original plugin, including native extension host, installation/diagnostic scripts, dependencies, docs, and skill |
| `resources/plugins/openai-bundled/plugins/unified-computer-use/` | `host/plugins/unified-computer-use/` | Complete original plugin and MCP configuration |
| `resources/codex` and `resources/codex-code-mode-host` | `host/bin/` | Original architecture-specific companion executables |

The narrower host integration inventory covers 750 files and 113 directories per architecture across those sources. Its destinations are aliases into the complete retained application. The original files retain their bytes and modes, including the Owl native shell, `app.asar`, native libraries, all original plugins, and all other application resources. LCU's additional integration configuration and extracted IAB declaration closure are separate from the original application.

Machine-readable records:

- Runtime: [ARM64](../scripts/runtime-inventory.arm64.json), [x86-64](../scripts/runtime-inventory.x64.json).
- Host integrations: [ARM64](../scripts/host-inventory.arm64.json), [x86-64](../scripts/host-inventory.x64.json).
- Complete application: [ARM64](../scripts/application-inventory.arm64.json), [x86-64](../scripts/application-inventory.x64.json).
- Every ASAR entry: [ARM64](../scripts/asar-inventory.arm64.json), [x86-64](../scripts/asar-inventory.x64.json).
- Agent-facing references: [all 195 original resources and their copies](../scripts/instructions.lock.json).

Each runtime inventory has a `files` map and a `surface` index. Categories describe files and never determine whether they are copied. Dependencies, optional methods, alternate modes, inactive platform branches, native modules, WASM resources, notices, and shared package files are all retained. Linux-only specialization occurs through the original runtime's own platform selection, not by deleting branches.

The ASAR inventory traces internal components instead of treating the archive as an opaque file. It records each entry's exact header metadata, packed offset, byte count, SHA-256, unpacked status, and link target when present. Packed content is hashed directly in chunks without extraction or execution. Every unpacked reference must match the complete application's independently recorded path, size, and content hash; `verify_application` checks those external files before `verify_asar` runs. All 57 internal package manifests, including nine unpacked manifests, have their public entrypoints and dependency fields indexed from hash-verified bytes.

The architecture comparison verifies that all 11,227 original core, preload, renderer, and webview JavaScript, HTML, and CSS source files have identical paths, sizes, and hashes in the two pinned packages. This includes the browser page preload and its renderer dependencies. Architecture-specific native modules and package metadata retain their own inventories. Matching source files establish source identity, not successful execution of every application feature.

## Public APIs and configuration

The `surface.package_interfaces` index records all 39 runtime package manifests and 18 host-plugin/dependency manifests, including their original `main`, `exports`, `imports`, `types`, `bin`, and dependency fields when present. This retains the following primary package entrypoints:

| Package | Original exported entrypoints | Role |
| --- | --- | --- |
| `@oai/cua` | `.` and `./tinyskyAlt` | Original CUA entrypoint and initialized unified API |
| `@oai/cua-repl` | `.`; `cua-repl` bin; `#instructions/*` imports | Original MCP/Node REPL launcher and instruction composition |
| `@oai/sky` | `.` and `./service` | Original native client and trusted RPC service |
| `@oai/browser-desktop` | `.` and `./service` | Original browser client and trusted browser service |

The `surface.api_declarations` index lists all 327 upstream runtime declaration files and 32 host-plugin/dependency declarations. The original files remain in their packages. In particular, the Linux `FullDesktopComputerUseClient` retains window/app discovery and activation, structured accessibility, screenshots, element and coordinate input, secondary actions, scrolling, typing, key chords, movement, relative movement, drag paths, held drag handles, and optional audio-recording methods. The original unified API retains native-window bindings, browser selection, tab selection/navigation, inventory, documentation replay, and `initialize` as a `getState` alias.

`surface.configuration_identifiers` indexes configuration names referenced by the original upstream JavaScript, declarations, Markdown, and JSON. It is a navigation index, not a new configuration schema. All source files are independently hashed, including options and transport implementations. Relevant original selectors include:

| Selector / source | Original responsibility |
| --- | --- |
| `CUA_REPL_ENABLED_SURFACES` | Enable native computer, browser, or both providers |
| `CUA_REPL_BROWSER_ENV` | Select Codex-app, cloud, training, or orbit browser guidance/runtime environment |
| `TINYSKY_ALT_INITIALIZE_DOCS` | Select the initial core guide when exposed by the host |
| `NODE_REPL_*` settings | Original executable/module paths, trusted services, environment exposure, sandbox/approval metadata, output/tool overrides, and host integration |
| `OAI_SKY_CONFIG_PATH` and platform selection | Original native runtime options |
| `OAI_SKY_LINUX_BIN` | Original Linux engine location override |
| `SKY_ENABLE_AUDIO` | Enable original optional Linux audio methods |
| Request metadata `openai/confirmation_policies` | Original browser/computer policy overrides |
| Request/session/turn metadata | Original browser routing, ownership, cleanup, and documentation replay behavior |

The complete option contracts live in the original declarations and implementations. Enumerating an option does not make its required external service available.

## Instruction and dynamic-document producers

Paths in this table are relative to `cua_node/lib/node_modules/` unless stated otherwise. Every producer is protected by the complete runtime file inventory.

| Producer | Sources and selection |
| --- | --- |
| `@oai/cua-repl/dist/lib/js/oai_js_cua_repl/src/instructions.js` | Selects `instructions/<platform>/` and browser environment guidance |
| `@oai/cua-repl/dist/lib/js/oai_js_cua_repl/src/launch.js` | Composes tool/server descriptions and initializes the original trusted services and banner |
| `@oai/cua/dist/lib/js/oai_js_cua/src/tinysky_alt/globals.js` | Initializes the enabled unified providers and adds the `initialize` alias |
| `@oai/cua/dist/lib/js/oai_js_cua/src/tinysky_alt/documentation.js` | Reads core/confirmation files and accepts valid host confirmation-policy overrides |
| `@oai/cua/dist/lib/js/oai_js_cua/src/tinysky_alt/create_tinysky_alt.js` | Delivers and replays core/policy text, alternate browser-API guidance, and selected-browser documentation |
| `@oai/browser-desktop/scripts/browser-service.mjs` | Builds browser documentation from API/document manifests, effective capabilities, environment, and original exclusions/policy metadata |
| `@oai/browser-desktop/scripts/browser-client.mjs` | Requests effective browser documentation and exposes the original browser APIs |
| `@oai/cua/dist/lib/js/oai_js_browser/dist/skill/scripts/` | Embedded original browser client/service and their reference inputs |
| `resources/plugins/openai-bundled/plugins/{browser,chrome}/scripts/` | Original plugin browser runtimes, installation, discovery, and diagnostics |

The `surface.dynamic_document_graphs` index stores all seven complete `documents.json` graphs: four runtime environments, the embedded browser runtime, and the browser and Chrome plugins. It preserves each resource's inclusion/lookup mode and conditions such as browser types, required API members, browser capabilities, and tab capabilities. Inventory capture rejects a graph that references a missing Markdown resource. Original `api.json` files and every referenced capability document are also hashed and retained, including inactive or unavailable capability branches.

See [INSTRUCTIONS.md](INSTRUCTIONS.md) for the exact instruction-resource roots, before-call reference delivery, and the small separate standalone wrapper.

## Verification interfaces

```sh
python3 scripts/inventory_runtime.py \
  --runtime /absolute/resources/cua_node --arch arm64 \
  --host-resources /absolute/resources
python3 scripts/inventory_asar.py \
  --asar /absolute/resources/app.asar --arch arm64
python3 scripts/inventory_asar.py --compare-architectures
```

The Python build interfaces are:

```python
from inventory_runtime import verify, compare, verify_host, verify_host_copy, verify_application
from inventory_asar import verify_asar, verify_shared_sources

verify(original_runtime, arch, root=repository)
verify(copied_runtime, arch, root=repository)
compare(original_runtime, copied_runtime)
verify_host(original_resources, arch, root=repository)
verify_host_copy(copied_host_directory, arch, root=repository)
verify_application(copied_application_directory, arch, root=repository)
verify_asar(copied_application_directory / 'resources/app.asar', arch, root=repository)
verify_shared_sources(root=repository)
```

`verify` compares the entire runtime tree and all surface metadata. Missing, added, modified, renamed, permission-changed, and symlink-retargeted entries fail. `verify_host` checks complete source integrations. `verify_host_copy` verifies every original host entry at its destination while allowing separate LCU-owned integration files. Package checksum verification precedes these checks. `--write` records a newly reviewed source inventory; it is a maintenance operation, not a way for release builds to accept drift.

`capture_application_package` generates the full application record directly from a checksum-verified Debian archive stream. It does not execute or extract package code. `verify_application` compares the installed complete tree, including its root permissions, against that record. The host alias check verifies both the expected relative destination and all original bytes beneath it.

`capture_asar` first checks the archive against the complete application inventory, then inventories every internal entry. Invalid content bounds, content hashes, unpacked references, and package-manifest bytes fail. The build invokes `verify_asar` immediately after `verify_application`; it rejects any difference from the reviewed architecture record. Capture's optional `--package-reference` directory supplies only unpacked package manifests and accepts each file only when its bytes match the selected architecture's pin. It is useful when auditing an ASAR extracted alone from a Debian stream; release verification reads manifests from the actual adjacent `app.asar.unpacked` tree.

## Scope boundary that still requires host evidence

The complete application inventory now includes the original `resources/app.asar` and native shell. The in-app browser and application-provided session, permission, approval, and cleanup behavior still require a functioning application host. Retaining those original bytes does not prove that the standalone host supplies their required state, services, or behavior.

Do not turn the complete `cua_node` inventory into a claim of complete Codex application parity. Host integration must be audited and exercised separately, including browser connection, real session/turn metadata, effective policy delivery, cancellation/cleanup, and agent-visible tool/output settings. Availability of each backend and equal task reliability require direct tests against the original Linux host and representative applications.
