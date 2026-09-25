# Pi origin approval dialog, 2026-09-25

Pi 0.73.0 rendered and accepted the adapter's interactive origin approval prompt in a real Pi terminal session. This verifies the Pi terminal renderer and acceptance path through the official MCP SDK fixture. It does not verify the original Chrome extension, browser state changes, or a paid model run.

## Setup and result

The bounded runner at `/private/tmp/lcu-pi-origin-dialog-20260925/run.mjs` launched Pi with the repository Pi adapter at `/private/tmp/lcu-finish-integration/adapters/pi/index.ts`, an isolated temporary Pi home, a local scripted OpenAI-compatible provider, and the official SDK fixture at `/private/tmp/lcu-finish-integration/adapters/test/mcp-fixture.mjs`. The fixture asked for approval to access exactly `http://127.0.0.1:8080`; the scripted provider instructed Pi to accept only that exact origin. No external model or browser was used.

On the second attempt, the captured PTY already showed `Allow Browser use to access http://127.0.0.1:8080?` with **Yes** selected at first inspection. The prompt was accepted, the provider received the fixture tool result `accept`, and the fixture logged `js` followed by `turn_ended` with `Stop` for the same session and turn. Pi exited with code 0; the runner reported `timedOut: false`. The saved evidence is `/private/tmp/lcu-pi-origin-dialog-20260925/attempt-2/summary.json`, `provider-requests.jsonl`, and `mcp-fixture.jsonl`.

The first attempt's output appeared only after its timeout, but that run did not capture timestamped PTY output or accept the prompt. The second attempt proves the prompt was already present when inspected; therefore the first apparent delay is consistent with buffered output and does not establish an adapter delay or defect.

This is fixture-backed Pi terminal evidence only. No claim is made here about original Chrome-origin handling, browser persistence, headers, or normal tab cleanup.
