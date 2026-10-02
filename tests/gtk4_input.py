"""Check what input reaches GTK 4 windows through the original runtime, with file oracles.

GTK 4 only reads input through XInput2. The original Linux engine sends a window-targeted
`pressKey`/`click` as core X events with XSendEvent, "without activating" the window, so a GTK 4
window never sees them. Desktop-level input (no `window`) uses the X server's XTEST path and
reaches GTK 4 normally, as xdotool does. AT-SPI actions and (in recent engines) `typeText` use neither path.
This test pins the paths that must work and prints, without asserting, what the window-targeted
path does, so a future change in the original engine shows up in the log instead of failing here.
"""
import json
import os
from pathlib import Path
import sys
import time
from mcp_client import Client, text

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

    # Informational: the window-targeted path (what app.pressKey and app.click use for coordinates).
    before = entry_text()
    run('try { await sky.press_key({window: pick("LCU GTK4 Entry"), key: "ctrl+a"});'
        ' await sky.press_key({window: pick("LCU GTK4 Entry"), key: "BackSpace"}); } catch (error) { nodeRepl.write(error.message); }')
    time.sleep(0.5)
    keys = 'delivered' if entry_text() != before else 'not delivered'
    run(f'try {{ await sky.click({{window: pick("LCU GTK4 Button"), x: 150, y: 80}}); }} catch (error) {{ nodeRepl.write(error.message); }}')
    time.sleep(0.5)
    click = 'delivered' if (output / 'Gtk4-click').exists() else 'not delivered'
    print(f'INFO: window-targeted input on GTK 4: keys {keys}, coordinate click {click}', flush=True)
    print('PASS: GTK 4 desktop-level text, keys, Return and coordinate click', flush=True)
finally:
    client.close()
