# Cual

Keep computer-use behavior in the original Codex Linux runtime. Do not add another accessibility, input, screenshot, browser, or MCP implementation. The Python files manage installation and desktop-session selection only.

Runtime changes require a pinned official package, documented source evidence, guarded projection, and real desktop integration tests on ARM64 and x86-64. Bundle the complete runtime and agent-registration dependencies in architecture-specific release archives. Downloads and projection belong to the build, never installation. Preserve upstream notices; Cual's MIT license does not relicense bundled dependencies.

Run `tests/run.sh` in disposable containers. Unit tests alone cannot prove desktop behavior. Preserve caller sandbox and approval settings. Never test against the user's personal desktop or copy agent credentials into fixtures.

Keep the installer compatible with the documented Luda-style options. Prefer upstream agent installers to new configuration adapters. Keep generated release archives in dist/ and out of Git. Test their installation and desktop behavior with network access disabled.
