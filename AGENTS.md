# LCU

Keep computer-use behavior in the original Codex Linux runtime. Do not add another accessibility, input, screenshot, browser, or MCP implementation. Standalone adapters may manage installation, desktop-session selection, and transport/lifetime wiring for original host services. Reuse original implementations and record each adaptation; missing host services remain parity blockers.

Runtime changes require a pinned official package, documented source evidence, and real desktop integration tests on ARM64 and x86-64. Ship thin architecture-specific LCU archives. During installation, acquire or select the exact pinned official Linux application, verify it before execution, and keep its original files and notices in a private versioned location. Never put OpenAI application binaries, copied instructions, or generated fragments in Git, releases, exports, or public images. LCU's MIT license does not relicense installed dependencies.

Run `tests/run.sh` in disposable containers. Unit tests alone cannot prove desktop behavior. Preserve caller sandbox and approval settings. Never test against the user's personal desktop or copy agent credentials into fixtures.

Keep the installer compatible with the documented Luda-style options. Prefer upstream agent installers to new configuration adapters. Keep generated release archives in dist/ and out of Git. Test offline installation from a verified local or cached official package with acquisition network access disabled. Browser/model services can still require network during use. Do not claim browser actions from discovery or an expected authentication failure.
