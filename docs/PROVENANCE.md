# Runtime provenance

Inspected and tested on 2026-09-22. The source of runtime truth is the official Linux distribution, not the macOS app or a reimplementation of its behavior.

## Primary sources

- [Official Linux app documentation](https://learn.chatgpt.com/docs/linux/linux-app): publishes Linux downloads and distinguishes product availability from the shipped package contents.
- [OpenAI ARM64 package index](https://persistent.oaistatic.com/codex-app-prod/linux/deb/dists/stable/main/binary-arm64/Packages) and [x86-64 index](https://persistent.oaistatic.com/codex-app-prod/linux/deb/dists/stable/main/binary-amd64/Packages): versioned artifact paths and SHA-256 values.
- [Official ARM64 package](https://persistent.oaistatic.com/codex-app-prod/linux/deb/pool/main/c/chatgpt/chatgpt_26.915.31945_arm64.deb) and [official x86-64 package](https://persistent.oaistatic.com/codex-app-prod/linux/deb/pool/main/c/chatgpt/chatgpt_26.915.31945_amd64.deb).
- [Luda v0.3.4 installer](https://github.com/0xpolarzero/luda/blob/e3863fb24dd28bda5910a8c2382a13afd4ee1064/scripts/install.sh), [registration](https://github.com/0xpolarzero/luda/blob/e3863fb24dd28bda5910a8c2382a13afd4ee1064/src/luda/setup.py), and [MIT license](https://github.com/0xpolarzero/luda/blob/e3863fb24dd28bda5910a8c2382a13afd4ee1064/LICENSE).

Package version: `26.915.31945`. Embedded runtime: `0.0.16/20260915001755-492f19756c31`. Embedded Node: `24.21.0`. Modules: `@oai/sky` 0.7.1, `@oai/cua` 0.2.5, `@oai/cua-repl` 0.1.0.

| Artifact | SHA-256 |
| --- | --- |
| ARM64 .deb | `b94c494b5f0fd7c720fa6fccd5ef609879affc62332ca930ed29b907d537bc6d` |
| x86-64 .deb | `d27a9c02919cfe484dcc5f34584b9ea9fd0d7a65c69dcc872b5bdcfa0efb5983` |

## Exact implementation seams

Paths below are relative to `usr/lib/chatgpt/resources/cua_node` in the verified package.

| Component | Source | Treatment |
| --- | --- | --- |
| JavaScript runtime | `bin/node` | Bundled unchanged at build time |
| MCP server and persistent execution | `bin/node_repl` | Copied unchanged; no substitute MCP implementation |
| Trusted Linux service | `lib/node_modules/@oai/sky/dist/project/cua/sky_js/src/service.js` | Bundled with original Linux dependencies |
| Linux actions and observations | `.../sky_js/src/targets/linux/` | Original implementation, including settling, compact IDs, screenshots, transport, and optional audio methods |
| Native desktop engine | `lib/node_modules/@oai/sky/bin/linux/sky_linux_{arch}` | Copied unchanged |
| Agent-facing API | `lib/node_modules/@oai/cua/dist/lib/js/oai_js_cua/src/tinysky_alt/create_tinysky_alt.js` | Retains Linux branch; removes other platforms and disables browser-provider branch |
| REPL launcher | `lib/node_modules/@oai/cua-repl/dist/lib/js/oai_js_cua_repl/src/launch.js` | Original launcher bundled with Linux instruction selection |
| Confirmation policy | `lib/node_modules/@oai/cua/docs/tinysky-alt-confirmations.md` | Bundled at build time; original metadata override behavior retained |

`project_runtime.py` has guarded transformations tied to the package hash. Unexpected source shapes abort the release build. The native action implementation is never rewritten. The build rejects dependencies on other platform engines or the browser provider, and rejects remaining platform dispatch in generated code. Generated build-input manifests and upstream notices remain beside the installed runtime.

Two documentation corrections are intentional: the shipped Linux entrypoint incorrectly accepts an app-name example, and the common API document mixes all platforms and browser providers. LCU documents observed Linux behavior: select an exact window ID, use window-relative coordinates, distinguish AT-SPI from X11 fallback, use pixel scrolling, and avoid unsupported `setValue`/`selectText`.

LCU's short launcher supplies explicit module search and trusted-code paths. The unmodified REPL isolates its trusted service as designed. No app login, OpenAI API key, desktop-app process, Codex CLI, or app socket was required in the isolated standalone tests. This does not prove application-level sandbox isolation or broad application compatibility.

## Distribution boundary

Architecture-specific release archives include the OpenAI runtime, its Linux projection, and all agent-registration dependencies. The build fetches and verifies the official package, projects Linux code, and packages the result with upstream notices. The installer only verifies and copies the bundled files. It has no download fallback and requires no .deb, npm, or build tool on the target machine. Generated archives live in dist/ and are excluded from source commits. The repository's MIT license applies to LCU-owned code and the MIT Luda-derived packaging code; bundled dependencies retain their own terms.

The Luda code supplies registration, validation, account ownership handling, portable export, and provisioning of pinned upstream `skills` 1.7.0 / `add-mcp` 2.4.0. No Luda screenshot, input, accessibility, browser, or MCP engine is used.

Updating the runtime requires inspecting the new official package, updating checksums and guarded transformations, and rerunning both architecture tests. Do not remove integrity checks or enable another desktop engine as a fallback.
