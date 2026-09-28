# Native macOS harness flows, 2026-09-28

OMP 18.4.1 passed a real model-driven native macOS edit/save flow with session approval. Hermes native verification and fresh-process reuse of an always grant remain pending. [Browser flows and the interactive approval matrices](harness-browser-flows-2026-09-28.md) passed separately.

## Environment and source boundary

The task-owned UTM guest `LCU macOS cold helper test` runs macOS 26.6.2 arm64 as `lcuverify` on `VirtualMac2,1`. Its [saved login procedure](macos-test-guest-access.md) was verified without changing the password. No test accessed the user's personal desktop.

The guest's installed `/Applications/ChatGPT.app` was reused in place. Its bundle identifier is `com.openai.codex`, version 26.917.62051, build 10789, signing team `2DC432GLL2`; deep strict signature verification passed. Its Node version is v24.21.0. LCU reports original runtime `0.0.16/20260915001755-492f19756c31`; the separate `@oai/cua-repl` package reports 0.1.0. The installed LCU prerequisite is 0.4.2.

The disposable test overlay used the committed OMP/Hermes adapters from `645520c` and three current lifecycle modules (`lcu/runtime.py`, `lcu/macos_host.py`, `lcu/macos_sky_service.mjs`) from the parallel macOS lifecycle work. This is not a clean-commit release verification. The private source manifest records each file hash. The original app and native helper were neither copied nor modified. Adapter dependencies and the selected app were linked from the existing guest installation.

The generated AppKit fixture was compiled on the host because the guest has no developer tools. Only this LCU-authored fixture binary was transferred, with SHA-256 `ef366e8205c0f6030315425cce7756f8af69f42419a66892f8381c7b6b2de724`. It generated a unique bundle identifier, saved the edited value to a separate file, and recorded its PID for exact cleanup. Its source/payload archive hash is `ae703adb1969d71ee50d7ac9fa4c83c7c8955d6afd6220ab9d7779beed6f2857`. No OpenAI binary or generated original instructions enter Git.

## OMP session approval

Official [OMP v18.4.1](https://github.com/can1357/oh-my-pi/releases/tag/v18.4.1) ran inside the guest with a fresh HOME and profile. The arm64 CLI hash is `f5b9bb407e685f92f32e6c14d6dab64570d2a0c85a6a19d74fdce38c64e07d14`. Model `glm-5.3-flash` used a bounded host proxy; the existing provider credential remained on the host, outside the guest and agent profile.

The actual OMP selector offered Allow once, Allow for this session, Always allow, and Decline. PTY input chose session once. The model made successive original CUA calls against generated app `dev.lcu.NativeFixture.df288fcf614a456188ed580a0eb4691c`, edited the text field, clicked Save draft, and inspected accessibility state and screenshots. The independent saved file contained exactly `lcu-omp-29f7289a678c`. After normal agent completion, a narrow observer recorded the successful original `turnEnded` response with `Stop`, session `01a0e7fc-1ffa-76da-9ad4-fa4f1476d8fb`, and turn `154ec513-d367-4cf4-bf16-201f03ad8fe5`, before test teardown.

The run passed in 88.88 seconds. Private evidence is `/private/tmp/lcu-harness-full-20260928/omp-macos-session-evidence.json`; the archived queue job is `d4084530-bda5-4245-a0e2-a8939a847a66`. Raw terminal output can contain original instructions and remains outside Git. The `agent_process_still_in_tui` field was sampled after teardown; it is not evidence that OMP exited on its own.

This proves actual macOS actions and reuse of session approval across calls within the same OMP turn. It does not establish grant reuse after an agent/helper restart, audio behavior, or other platforms.

For guests without developer tools, build only the generated fixture with `xcrun swiftc -O -framework AppKit tests/macos_native_fixture.swift -o /path/to/private/staged/tests/macos_native_fixture.bin`. Place that binary beside the staged fixture shell and Swift source. The shell uses it instead of invoking the guest compiler. The binary is excluded from Git; the optional `LCU_FIXTURE_PID_FILE` records the exact fixture process for cleanup.
