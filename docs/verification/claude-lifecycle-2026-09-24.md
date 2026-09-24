# Claude Code lifecycle boundary and manual probe

LCU currently registers the original MCP server and generated skill in Claude Code. It does **not** register a lifecycle hook. This is an explicit integration limit: the original CUA plugin calls its hidden `turn_ended` tool on `Stop`, `Interrupt`, and `SubagentStop`, passing both `session_id` and `turn_id`. The selected app's source is `plugins/openai-bundled/plugins/unified-computer-use/.codex-plugin/plugin.json`; LCU's adaptation is in `lcu/codex_hooks.py`.

Claude Code's current [hook reference](https://code.claude.com/docs/en/hooks) says `Stop` runs when the main agent finishes but **does not run on user interrupt**; API errors use `StopFailure`. `SessionEnd` runs when the whole session exits, with no per-turn interrupt reason. [MCP tool hooks](https://code.claude.com/docs/en/hooks#MCP-tool-hook-fields) can call an already-connected server and interpolate hook input. `Stop` supplies `session_id`, but its documented input does not supply `turn_id`. The [MessageDisplay input](https://code.claude.com/docs/en/hooks#MessageDisplay-input) has `turn_id`, but a display batch is not guaranteed before a tool call. Copying the original Stop hook with `${turn_id}` would therefore not provide the original call metadata, and no Claude Code hook provides reliable cleanup immediately after a user interrupts a still-open session. The installed Claude Code 2.1.204 native binary contains `MessageDisplay`, `StopFailure`, and `SessionEnd` event strings but no `UserInterrupt` string; this string inspection is corroborating evidence, not a live event test.

The official [Claude Agent SDK](https://github.com/anthropics/claude-agent-sdk-typescript) has a V1 streaming `Query.interrupt()` control. An SDK launch adapter could own the interrupt decision, but it would be a separate headless program rather than the normal interactive `claude` CLI. It would also need an MCP bridge to stamp one turn ID across original `js` calls and forward images and elicitation. Anthropic's [SDK V2 interrupt issue](https://github.com/anthropics/claude-agent-sdk-typescript/issues/120) records that its preview session interface lacks `interrupt()`. No SDK adapter is shipped or claimed here. This machine's Claude launcher deliberately blocks automated runs, and using the SDK's bundled executable would evade that guard.

## Prepared manual falsification

The probe writes only to a new private temporary project. It generates the selected app's full local skill in that project, registers an LCU MCP command there, and installs project-local hooks that log only event names and session IDs. It never starts Claude, copies account credentials, records prompts, or changes personal Claude settings.

```sh
python3 tests/claude_lifecycle_probe.py prepare \
  --release /absolute/path/to/installed/lcu/current \
  --output /private/tmp/lcu-claude-lifecycle-probe
cd /private/tmp/lcu-claude-lifecycle-probe/project
# In the owner's interactive shell, intentionally start the guarded `clod` launcher.
```

Once Claude starts, confirm the project MCP and skill are visible. Give it this normal-completion task: “Read the local LCU skill. Use LCU's original `js` tool to evaluate `1+1` and then `2+2` in separate calls, and report both results. Do not use the desktop or browser.” After it finishes, inspect `../events.jsonl` for `PreToolUse`, `PostToolUse`, and `Stop` with one session ID.

Then give it this interrupt task: “Use LCU `js` to set `globalThis.lcuProbe = 7`, then in a separate `js` call wait for 30 seconds before reporting the value. Do not use the desktop or browser.” Once the waiting tool call starts, interrupt Claude using its normal interactive control. Inspect the new lines in `../events.jsonl`; any `Stop`, `StopFailure`, or other event that runs immediately on interrupt would change the source-only conclusion. A missing event confirms this installed version cannot notify the original CUA server at that point through hooks. The probe does not claim a live Claude result until a person deliberately runs it and records the output.

The recorder itself was checked with a synthetic hook payload: it wrote only `{"event":"Stop","session_id":"session-1"}` with file mode `0600`, discarding a supplied prompt and transcript path. `prepare` succeeded against the installed macOS LCU release at `/private/tmp/lcu-delivery-install/current` without launching Claude.
