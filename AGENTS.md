# Cual

Keep computer-use behavior in the original Codex Linux runtime. Do not add another accessibility, input, screenshot, browser, or MCP implementation. The Python files manage installation and desktop-session selection only.

Runtime changes require a pinned official package, documented source evidence, guarded projection, and real desktop integration tests on ARM64 and x86-64. Do not vendor OpenAI runtime files or imply that this repository licenses them.

Run `tests/run.sh` in disposable containers. Unit tests alone cannot prove desktop behavior. Preserve caller sandbox and approval settings. Never test against the user's personal desktop or copy agent credentials into fixtures.

Keep the installer compatible with the documented Luda-style options. Prefer upstream agent installers to new configuration adapters. Keep generated packages, binaries, screenshots, and test environments out of Git.
