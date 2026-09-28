# Harness browser flows, 2026-09-28

These tests run the actual harness UI on macOS against an isolated Linux ARM64 browser desktop. They do not prove macOS native desktop control. The task-owned macOS guest is locked at its login screen; its new OMP/Hermes native tests remain pending.

The disposable containers have no network, personal home, credentials, or host desktop mounts. They run official Chrome 154.0.8037.57 with the original extension 1.26.901.11451. A verified LCU 0.4.1 archive was installed offline into a fresh prefix, reusing the image's already-installed OpenAI app 26.915.31945 and original CUA runtime 0.0.16/20260915001755-492f19756c31. Chrome retains its sandbox. A host-loopback proxy provides bounded access to `glm-5.3-flash`; the provider credential remains in the host proxy and is never copied into the harness profiles or containers.

## OMP

Official OMP [v18.4.1](https://github.com/can1357/oh-my-pi/releases/tag/v18.4.1) passed the real model-driven flow in a fresh profile. Its interactive selector asked for the exact local origin, and PTY input selected Allow. The model used the original `cua.createBrowserTab`, filled the generated page, clicked Save draft, and verified the displayed result. The independent container oracle contained exactly `omp-browser-d115ff7bce28`; `Other.txt` was absent. An OMP `agent_end` observer fired, and the independent Chrome target inventory contained only `about:blank` before the harness process was terminated. The generated session tab therefore closed during normal turn cleanup.

The final run used the clean source snapshot at `/private/tmp/lcu-harness-latest-20260928/committed-source`, excluding unrelated working-tree changes. Private evidence is `/private/tmp/lcu-harness-full-20260928/omp-browser-evidence.json`; it records the binary, adapter, and shared-client hashes, approval observation, exact file contents, and browser targets before process shutdown. Raw transcripts can contain original runtime instructions and remain outside Git.

`tests/harness_browser_fixture.py` serves the generated local page. `tests/harness_browser_session.sh` starts the isolated Chrome fixture. `tests/omp_browser_live.py` registers the native harness plugin, runs the actual model and UI, observes turn completion, and checks the independent oracles. It accepts an explicit `--release` to test a clean source snapshot. Browser setup and extension readiness alone are not counted as a browser action.

The separate [OMP approval matrix](omp-compatibility-2026-09-28.md) covers nine real TUI decisions using a scripted provider and MCP fixture. It verifies exact scope responses, denial, and dismissal, but does not establish persistence across original-runtime restarts.
