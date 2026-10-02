# Linux window-targeted input: measurements and LCU 0.8.3 translation

Date: 2026-10-02. Supports the [Linux window-targeted input adaptation](../STANDALONE-ADAPTATIONS.md#linux-window-targeted-input-reason-and-removal-criterion). All runs used disposable Ubuntu 24.04 containers with local fixtures; no real harness configuration, account or desktop was used, and no OpenAI binary is redistributed.

## Measurement (LCU 0.8.2 and ChatGPT 26.928.31416, CUA 0.0.27)

Native linux/arm64 Docker, Xvfb 1280x800 with XTEST, Xfwm4 4.18, a D-Bus session with AT-SPI, and the original `node_repl` sandbox active. Driven through LCU's stdio MCP `js` tool. Every observation is a file, an AT-SPI text and caret offset, or a DOM event posted by the fixture, never a call's success. Each trial first seeded state with plain XTEST, then ran the action on the path under test.

W is the window-targeted path (`app.pressKey`, `app.click`, `app.scroll`, `app.drag` with a window, which the engine sends with `XSendEvent`). D is `sky.activate_window` followed by the desktop-level `sky.*` call with screen coordinates (XTEST). `ok` means the oracle changed, `NO` means the call succeeded and nothing happened.

| App (toolkit) | keys | click | scroll | drag |
| --- | --- | --- | --- | --- |
| GTK 3 fixture, gedit 46.2 | W ok, D ok | W ok, D ok | W ok, D ok | W ok, D ok |
| **GTK 4 fixture, gnome-text-editor 46.3** | **W NO**, D ok | **W NO**, D ok | **W NO**, D ok | **W NO**, D ok |
| Qt 5 (PyQt5 5.15.13), Qt 6 (PyQt6 6.4.2) | W ok, D ok | W ok, D ok | **W NO**, D ok | W ok, D ok |
| Java 21 Swing | W ok only if already focused, D no right after `activate_window` | W ok, D ok | W ok, D ok | W ok, D ok |
| Firefox 157, Chrome for Testing 153, Electron 44 | W ok, D ok | W ok, D ok | W ok, D ok | W ok, D ok |
| xfce4-terminal (VTE) | W ok, D ok | W ok, D ok | W ok, D ok | not applicable |

- Only the whole GTK 4 toolkit ignored window-targeted keys, clicks, scroll and drag, and only Qt ignored scroll. Browsers, Electron, GTK 3 and the terminal also worked unfocused and occluded, without raising or focusing the target.
- Raw delivery (a core-only Xlib window logging events): the engine's window-targeted click arrives as a `ButtonPress` with `send_event=1` at the given coordinates; the same action through the desktop path arrives with `send_event=0` at `window.x + x`, `window.y + y`. GTK 4 reads XInput2 only, so it never sees the `XSendEvent` core events.
- `sky.list_windows` returns `{id, x, y, width, height, focused, modal, window_type, title, app}`; `x, y` is the X client origin, equal to `xwininfo`'s absolute upper-left and excluding the Xfwm4 frame. Window-targeted coordinates are client relative, so the desktop point is `(window.x + x, window.y + y)`. A GTK 3 client-side-decorated window reported a shadow-including origin (`-26,-23` for gedit) that is still consistent with that window's own coordinates. HiDPI (`GDK_SCALE=2`) uses device pixels on both paths, so no scaling is applied.
- `activate_window` succeeded within 20 to 30 ms for every app under Xfwm4 and `list_windows().focused` agreed. Java (Globally Active focus) drops keyboard focus when an already active window is activated again, which is why the translation never activates a window that is already focused and never touches Java.
- A modal GTK dialog is listed as its own window (`modal: true`, focused) and the parent as unfocused. A window-targeted key to the parent did nothing, and activating the parent did not help a following desktop key (the toolkit's grab); the dialog must be the target.
- `typeText` is AT-SPI only: it works for GTK 3, GTK 4 and Qt (with accessibility on), and errors with "no AT-SPI provider" for Firefox, Chromium, Electron, Java and VTE. gedit 46.2 segfaulted on AT-SPI text insertion with either path (a separate bug, not changed here).
- Controls: plain `xdotool` works everywhere; `xdotool --window` (also `XSendEvent`) is ignored by GTK 3 and GTK 4 but accepted by Qt, Firefox, Chromium, Electron and Java.

Not measured: fractional scaling, other window managers or compositing, real Google Chrome (Chrome for Testing stood in), an Electron app beyond a minimal page.

## What 0.8.3 does

`lcu/linux_sky_service.mjs` is the `sky` trusted service on Linux. It forwards to the original Sky service and, for window-targeted `key`, `click`, `scroll`, `drag`, `move`, `key_down` and `key_up` on a GTK 4 process (and `scroll` on a Qt process), activates the target if it is not focused and issues the engine's desktop-level call with converted coordinates. The process is identified by `_NET_WM_PID` and `/proc/<pid>/maps` (`libgtk-4.so`, `libQt5Core.so` or `libQt6Core.so`; a process that also maps `icudtl.dat`, `libxul.so` or `libffmpeg.so` is not GTK 4). Details and limits: [adapters](../ADAPTERS.md#linux-window-targeted-input).

## Tests

`tests/gtk4_input.py` and `tests/gtk4_surface_fixture.py` (GTK 4: keys, chords, held modifier, click on an unfocused window, scroll offset, drag displacement, a modal dialog, a missing window, `LCU_LINUX_INPUT_TRANSLATION=off`), `tests/linux_input_controls.py` with `tests/qt_fixture.py` (GTK 3 click, a core-event X11 window, Qt keys and click, a Chromium-like process, Qt scroll translated and untranslated with the opt-out control; the focused window stays the same wherever the original path is kept) and `tests/adapter_paths.py` (GTK 4 window-targeted keys and click through the bare client, Codex relay, Claude relay, the Pi/Oh My Pi shared client and the Hermes bridge). `tests/codex_mcp_env.py` records that Codex CLI 0.159.1 drops an LCU variable from its own environment and passes one set under `[mcp_servers.lcu.env]`, directly and behind the relay.

Gate results are in the [0.8.3 release notes](../releases/0.8.3.md).

## 0.8.4: review findings fixed

A review of 0.8.3 found seven defects in the translation. The service-level ones were reproduced before the fix with an in-memory fake desktop (`adapters/test/linux-sky-service.test.mjs`: window list and focus, desktop-level input with a held-key model, `xprop` and `/proc`), which failed 14 of 19 cases against the 0.8.3 logic:

1. Planning ran before serialization on a stale focus snapshot: concurrent requests to B then A activated B and then sent A's key to B. Planning, activation and verification now all run inside the queue, the focus is verified immediately before sending, and a mismatch is an error.
2. Translated holds lost their release routing: after the target closed or minimized, `key_up` became a window-targeted no-op and the desktop key stayed down, and `down(A,shift) down(B,shift) up(A,shift)` released B's. Holds are tracked per (target, chord) with per-key owner counts and always released at the desktop level; the effect oracle is a later desktop `k` typed in lowercase.
3. A stale point could click another application: the start point of pointer actions is validated against the target's current client rectangle.
4. Modal redirection kept the parent's geometry: it is now keyboard only, and pointer input to such a parent is an error naming the dialog.
5. A caller-supplied `NODE_REPL_TRUSTED_SERVICES` (`{}` or custom-only) received an added `sky` entry: supplied maps are now kept verbatim unless they name the original Sky service.
6. The toolkit cache survived PID reuse: it is keyed by (PID, `/proc/<pid>/stat` start time) and revalidated.
7. `_NET_WM_PID` of a window from another machine or PID namespace was trusted: `WM_CLIENT_MACHINE` must equal the local host name and `/proc/<pid>/ns/pid` must equal LCU's own, otherwise the request is untouched.

The desktop suites gained a hold released after its window closed (the stuck-shift effect oracle), refused pointer input to a modal parent and an out-of-bounds click refusal. Gate results are in the [0.8.4 release notes](../releases/0.8.4.md).
