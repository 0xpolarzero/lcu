# Oh-my-pi compatibility review, 2026-09-28

LCU now registers an OMP harness by linking a generated native plugin package in the selected OMP profile. OMP v18.1.6 RPC tests in isolated user profiles discovered the `/lcu` extension command and linked `lcu` skill. A fake-provider host test verified first-request LCU tool presentation and dispatch through the adapter. Project scope is rejected because OMP's native link CLI currently writes to the profile registry regardless of `--scope`; setup must not label that write as project-scoped. These tests used temporary profiles and fixtures; they do not validate a desktop action or desktop support.

## LCU evidence

- Setup adds the `omp` harness using the shared Pi adapter and installs a generated package with OMP's native `omp.extensions` manifest through the profile-scoped `omp plugin link` command. OMP project scope is not supported.
- The generated wrapper imports the shared adapter by a relative path so OMP's compiled loader can resolve its transitive package graph. It enables eager connection and OMP's `essential` presentation for LCU tools; Pi tool registration keeps its existing behavior.
- The generated package includes the full LCU skill under `skills/lcu/`. OMP's actual RPC command list reports it with `source: "skill"`.
- [Current host verification](latest-standalone-harness-2026-09-27.md) covers Pi 0.87.1; it is separate from the OMP v18.1.6 fixtures described here.

## Upstream evidence

These primary sources were inspected on 2026-09-28 on OMP's mutable `main` branch, not a pinned release:

- [Extension loading](https://github.com/can1357/oh-my-pi/blob/main/docs/extension-loading.md) documents `pi.extensions` manifest compatibility, package extension discovery, and explicit `--extension`/`-e` paths. Plugin packages can use `omp.extensions`; OMP also scans linked plugin packages' conventional `skills/` directory.
- [Extension API types](https://github.com/can1357/oh-my-pi/blob/main/packages/coding-agent/src/extensibility/extensions/types.ts) expose the same five tool execution arguments used by LCU, define `before_agent_start.systemPrompt` and its replacement as `string[]`, and default extension tools to `loadMode: "discoverable"`. LCU's two core tools opt into `loadMode: "essential"` for OMP so the model sees them in the initial tool list.
- [Extension runner](https://github.com/can1357/oh-my-pi/blob/main/packages/coding-agent/src/extensibility/extensions/runner.ts) passes the prompt array to `before_agent_start` handlers and accepts a returned string by wrapping it in an array. LCU now appends its instructions as one new array entry for OMP and keeps the original string behavior for Pi.
- The [compiled Pi compatibility loader](https://github.com/can1357/oh-my-pi/blob/main/packages/coding-agent/src/extensibility/plugins/legacy-pi-compat.ts) traverses relative imports to resolve transitive dependencies. A `file://` wrapper failed SDK resolution in OMP 18.1.6; the relative import passed the real host test.
- [Extension loader](https://github.com/can1357/oh-my-pi/blob/main/packages/coding-agent/src/extensibility/extensions/loader.ts) records event handlers directly and notifies listeners when tools are registered. This supports tools registered during `before_agent_start`.
- [Plugin manager installer plumbing](https://github.com/can1357/oh-my-pi/blob/main/docs/plugin-manager-installer-plumbing.md) describes linked plugin paths, enabled-plugin discovery, extension manifests, and conventional skill discovery. [Plugin CLI](https://github.com/can1357/oh-my-pi/blob/main/packages/coding-agent/src/commands/plugin.ts) exposes `omp plugin link --scope user|project <path>`; `user` is the default.
- The actual [plugin-link CLI handler](https://github.com/can1357/oh-my-pi/blob/main/packages/coding-agent/src/cli/plugin-cli.ts) currently calls the profile plugin manager without forwarding `--scope`. The flag is therefore not evidence of project registration for this command; LCU refuses project scope rather than writing into a profile behind the user's back.
- [Extension documentation](https://github.com/can1357/oh-my-pi/blob/main/docs/extensions.md) documents `ctx.ui.select()` and session/agent lifecycle events. OMP defines `session_shutdown`, but its documented SIGTERM/SIGHUP/uncaught-exit path skips session disposal and that event (see [upstream issue #4055](https://github.com/can1357/oh-my-pi/issues/4055)).

## Verification and limits

OMP and Pi share the adapter's relevant tool callback, `registerTool`, command, UI selection, elicitation, and lifecycle surfaces. OMP's `before_agent_start` prompt is an array; LCU now appends without flattening existing blocks. `adapters/test/omp.test.mjs` models that host shape and verifies prompt preservation, dynamic tool registration, result forwarding, and normal `Stop` cleanup through the original stdio MCP fixture. Existing Pi tests continue to cover approval decisions and cancellation.

The current evidence covers prompt-array preservation and model tool advertisement/dispatch through a fake provider, native extension and skill registration, and normal `Stop` cleanup. It does not cover approval selection/cancellation through OMP UI or desktop actions. Desktop claims still require the repository's disposable desktop integration tests.

Reproduce the native checks with `python3 tests/omp_registration.py --omp /absolute/path/to/omp` and `OMP_BIN=/absolute/path/to/omp python3 tests/omp_host.py`. They use synthetic MCP/provider fixtures, temporary HOME/XDG/profile directories, and no agent credentials or personal desktop. The host fixture observed a two-second `session_shutdown` hook timeout after successful matching `Stop` cleanup; shutdown completion is not claimed.

The final `tests/run.sh linux/arm64` gate passed with the verified pinned local package: 214 Python tests, offline installation, existing Codex/Claude Code/Pi registration checks, and the disposable Linux GTK desktop suite. Evidence archive: `.verification/arm64.5fnpEe`. The 16 focused Pi/OMP adapter tests passed. The broader Node adapter run had an intermittent Codex progress-notification assertion failure; the unchanged HEAD Codex fixture passed in isolation, so the broader suite is not recorded as green. These checks do not extend OMP or Hermes desktop claims.
