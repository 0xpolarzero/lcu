"""Check what input reaches GTK 4 windows through LCU and the original runtime, with file oracles.

GTK 4 only reads input through XInput2. The original Linux engine sends a window-targeted
`pressKey`/`click`/`scroll`/`drag` as core X events with XSendEvent, "without activating" the window,
so a GTK 4 window never sees them. Desktop-level input (no `window`) uses the X server's XTEST path and
reaches GTK 4 normally, as xdotool does. AT-SPI actions and (in recent engines) `typeText` use neither path.
This test pins the desktop-level paths, then proves that LCU's Linux input translation
(lcu/linux_sky_service.mjs) makes the window-targeted calls work for GTK 4: keys, coordinate click, scroll,
drag, a modal dialog, and that `LCU_LINUX_INPUT_TRANSLATION=off` restores the original behavior.
The oracles are files the independent fixtures write, never a call's success.
"""
import json
import os
from pathlib import Path
import sys
import time
from mcp_client import Client, text
import linux_input_support as support

command = sys.argv[1:] or ['/opt/lcu/current/bin/lcu']
output = Path(os.environ['LCU_TEST_OUTPUT'])
client = Client(command)


def run(code, error=False):
    return text(client.js(code, error=error))


def entry_text():
    path = output / 'Gtk4-entry.txt'
    return path.read_text() if path.exists() else ''


def settle(predicate, attempts=30):
    for _ in range(attempts):
        if predicate():
            return True
        time.sleep(0.1)
    return False


def window_targeted(command):
    """Window-targeted input to GTK 4 windows, through `sky.*` and the `app.*` helpers."""
    support.start_fixture('gtk4_surface_fixture.py')
    session = support.Session(command)
    try:
        surface = session.window('LCU GTK4 Surface')
        entry_window = session.window('LCU GTK4 Entry')
        button_window = session.window('LCU GTK4 Button')
        # Start from a different focused window: the translation must focus the target itself.
        session.activate('LCU GTK4 Button')
        session.run(f'await sky.press_key({{window: await byTitle("LCU GTK4 Surface"), key: "x"}});')
        assert support.settle(lambda: support.read('Gtk4Surface-entry.txt') == 'x'), support.read('Gtk4Surface-entry.txt')
        assert session.focused_id() == surface['id'], 'the translated key should leave the target focused'
        # The app helpers use the same path: chord, Return through the entry, and BackSpace.
        session.run(f'let app = await cua.getApp({{windowId:{surface["id"]}}});'
                    'await app.pressKey("ctrl+a"); await app.pressKey("BackSpace");')
        assert support.settle(lambda: support.read('Gtk4Surface-entry.txt') == ''), support.read('Gtk4Surface-entry.txt')
        session.run('await app.pressKey("y");')
        assert support.settle(lambda: support.read('Gtk4Surface-entry.txt') == 'y')
        # key_down/key_up pair (engines from CUA 0.0.27 on): a held shift types a capital.
        if session.run('nodeRepl.write(typeof sky.key_down === "function" ? "yes" : "no");') == 'yes':
            session.run('await sky.key_down({window: await byTitle("LCU GTK4 Surface"), key: "shift"});'
                        'await sky.press_key({window: await byTitle("LCU GTK4 Surface"), key: "k"});'
                        'await sky.key_up({window: await byTitle("LCU GTK4 Surface"), key: "shift"});')
            assert support.settle(lambda: support.read('Gtk4Surface-entry.txt') == 'yK'), support.read('Gtk4Surface-entry.txt')
        else:
            print('INFO: this engine has no key_down/key_up; hold translation not exercised', flush=True)
            session.run('await sky.press_key({window: await byTitle("LCU GTK4 Surface"), key: "shift+k"});')
            assert support.settle(lambda: support.read('Gtk4Surface-entry.txt') == 'yK'), support.read('Gtk4Surface-entry.txt')

        # Coordinate click on another, unfocused window: window-relative coordinates.
        session.activate('LCU GTK4 Surface')
        session.run(f'let button = await cua.getApp({{windowId:{button_window["id"]}}});'
                    'await button.click([150, 80]);')
        assert support.settle(lambda: (support.output / 'Gtk4-click').exists()), 'window-targeted click did not reach GTK 4'
        (support.output / 'Gtk4-click').unlink()
        assert session.focused_id() == button_window['id']
        # An AT-SPI element action is not translated and still works.
        state = session.run('nodeRepl.write(await button.getAXState());')
        assert 'Press' in state, state

        # Scroll over the scrolled area: coordinates relative to the surface window (client origin).
        session.run('await app.scroll([200, 330], "down", {pixels: 300});')
        assert support.settle(lambda: int(support.read('Gtk4Surface-scroll.txt') or 0) > 0), support.read('Gtk4Surface-scroll.txt')
        # Drag inside the drag area.
        session.run('await app.drag([40, 70], [190, 100]);')
        assert support.settle(lambda: support.read('Gtk4Surface-drag.txt') is not None), 'drag did not reach GTK 4'
        dx, dy = map(int, support.read('Gtk4Surface-drag.txt').split(','))
        assert 120 <= dx <= 180 and 15 <= dy <= 45, (dx, dy)

        # A modal dialog owned by the target receives keys addressed to its parent.
        before = support.read('Gtk4Surface-entry.txt')
        (support.output / 'Gtk4Surface-open-modal').write_text('1')
        modal = session.window('LCU GTK4 Modal')
        session.activate('LCU GTK4 Entry')
        session.run(f'await sky.press_key({{window: await byTitle("LCU GTK4 Surface"), key: "m"}});')
        assert support.settle(lambda: support.read('Gtk4Surface-modal-entry.txt') == 'm'), support.read('Gtk4Surface-modal-entry.txt')
        assert support.read('Gtk4Surface-entry.txt') == before, 'the parent received a key meant for the modal dialog'
        assert session.focused_id() == modal['id']
        # Pointer input to the parent of a modal dialog is refused (the parent's coordinates do not describe the
        # dialog); the dialog itself can still be targeted explicitly.
        refused = session.run('try { await sky.click({window: await byTitle("LCU GTK4 Surface"), x: 40, y: 40}); nodeRepl.write("no error"); }'
                              ' catch (error) { nodeRepl.write("error: " + error.message); }')
        assert refused.startswith('error: ') and 'modal' in refused, refused
        assert session.focused_id() == modal['id']
        if session.run('nodeRepl.write(typeof sky.key_down === "function" ? "yes" : "no");') == 'yes':
            # A translated hold taken on the dialog is released at the desktop level after the dialog closed.
            session.run('globalThis.dialog = await byTitle("LCU GTK4 Modal");'
                        'await sky.key_down({window: dialog, key: "shift"});')
            (support.output / 'Gtk4Surface-close-modal').write_text('1')
            assert support.settle(lambda: all(w.get('title') != 'LCU GTK4 Modal' for w in session.windows()))
            session.run('await sky.key_up({window: dialog, key: "shift"});')
            session.activate('LCU GTK4 Surface')
            before = support.read('Gtk4Surface-entry.txt')
            session.run('await sky.press_key({key: "k"});')
            assert support.settle(lambda: support.read('Gtk4Surface-entry.txt') == before + 'k'), \
                ('a hold on a closed window was left active', before, support.read('Gtk4Surface-entry.txt'))
            session.run('await sky.press_key({window: await byTitle("LCU GTK4 Surface"), key: "ctrl+a"});'
                        'await sky.press_key({window: await byTitle("LCU GTK4 Surface"), key: "BackSpace"});')
            assert support.settle(lambda: support.read('Gtk4Surface-entry.txt') == '')
            (support.output / 'Gtk4Surface-open-modal').write_text('1')
            session.window('LCU GTK4 Modal')
        (support.output / 'Gtk4Surface-close-modal').write_text('1')
        assert support.settle(lambda: all(w.get('title') != 'LCU GTK4 Modal' for w in session.windows()))
        session.activate('LCU GTK4 Entry')

        # A point outside the target window's client rectangle is refused instead of clicking whatever is there.
        outside = session.run('try { await sky.click({window: await byTitle("LCU GTK4 Button"), x: 5000, y: 5000}); nodeRepl.write("no error"); }'
                              ' catch (error) { nodeRepl.write("error: " + error.message); }')
        assert outside.startswith('error: ') and 'outside' in outside, outside
        assert not (support.output / 'Gtk4-click').exists()
        assert session.focused_id() == entry_window['id'], 'a refused click must not change focus'

        # A window that is not listed keeps the engine's own error; nothing is sent to the desktop.
        error = session.run('try { await sky.press_key({window: {app: "x11:1", id: 1, title: "gone", x: 0, y: 0, width: 5, height: 5, focused: false, modal: false, window_type: "normal"}, key: "q"}); nodeRepl.write("no error"); } catch (error) { nodeRepl.write("error: " + error.message); }')
        assert error.startswith('error: '), error
        assert session.focused_id() == entry_window['id']
    finally:
        session.close()

    # Opt-out: the original engine behavior returns, including the focus-free, ineffective delivery.
    off = support.Session(command, env={**os.environ, 'LCU_LINUX_INPUT_TRANSLATION': 'off'})
    try:
        off.activate('LCU GTK4 Entry')
        before = support.read('Gtk4Surface-entry.txt')
        off.run('await sky.press_key({window: await byTitle("LCU GTK4 Surface"), key: "z"});'
                'await sky.click({window: await byTitle("LCU GTK4 Button"), x: 150, y: 80});')
        time.sleep(1)
        assert support.read('Gtk4Surface-entry.txt') == before, 'translation was not disabled'
        assert not (support.output / 'Gtk4-click').exists(), 'translation was not disabled'
        assert off.focused_id() == entry_window['id'], 'the original path must not change focus'
    finally:
        off.close()
        support.stop_fixtures()


try:
    run('await cua.getState();')
    for _ in range(50):
        windows = json.loads(run('nodeRepl.write(JSON.stringify(await cua.listWindows({emit:false})));'))
        found = {w['title']: w for w in windows if w.get('title') in ('LCU GTK4 Entry', 'LCU GTK4 Button')}
        if len(found) == 2:
            break
        time.sleep(0.2)
    assert len(found) == 2, windows
    entry, button = found['LCU GTK4 Entry'], found['LCU GTK4 Button']
    run('var {sky} = await import("@oai/sky"); globalThis.windows = await sky.list_windows();'
        'globalThis.pick = title => windows.find(w => w.title === title);')

    # Informational: `typeText` is not one input path across app versions. ChatGPT 26.928 inserts through
    # AT-SPI, which GTK 4 accepts (it may report a caret error afterwards); 26.915 inserted nothing here.
    run(f'let app = await cua.getApp({{windowId:{entry["id"]}}}); '
        'try { await app.typeText("alpha"); } catch (error) { nodeRepl.write("typeText: " + error.message); }')
    inserted = settle(lambda: entry_text() == 'alpha')
    print(f'INFO: app.typeText on a GTK 4 entry: {"inserted" if inserted else "inserted nothing"}', flush=True)

    # Desktop-level keys reach GTK 4: focus the window, then press with no `window`.
    run('await sky.activate_window({window: pick("LCU GTK4 Entry")});'
        'await sky.press_key({key: "ctrl+a"}); await sky.press_key({key: "BackSpace"});')
    assert settle(lambda: entry_text() == ''), entry_text()
    run('await sky.type_text({text: "gamma"});')
    assert settle(lambda: entry_text() == 'gamma'), entry_text()
    run('await sky.press_key({key: "ctrl+a"}); await sky.press_key({key: "BackSpace"});')
    assert settle(lambda: entry_text() == ''), entry_text()
    run('await sky.type_text({text: "beta"}); await sky.press_key({key: "Return"});')
    assert settle(lambda: entry_text() == 'beta' and (output / 'Gtk4-activated').exists()), entry_text()

    # A desktop-level coordinate click reaches GTK 4 (window geometry from the original list).
    run('await sky.activate_window({window: pick("LCU GTK4 Button")});')
    click_x, click_y = button['x'] + button['width'] // 2, button['y'] + button['height'] // 2
    run(f'await sky.click({{x: {click_x}, y: {click_y}}});')
    assert settle(lambda: (output / 'Gtk4-click').exists()), 'desktop-level click did not reach GTK 4'
    (output / 'Gtk4-click').unlink()

    # Window-targeted input (what app.pressKey/app.click/app.scroll/app.drag send) reaches GTK 4 through
    # LCU's translation to the engine's desktop-level calls. The windows below observe what arrived.
    window_targeted(command)
    print('PASS: GTK 4 desktop-level text, keys, Return and coordinate click', flush=True)
finally:
    client.close()
