"""Exercise the installed MCP command, with independent GTK and file oracles."""
import json
import os
from pathlib import Path
import re
import sys
import time
from mcp_client import Client, text

command = sys.argv[1:] or ['/opt/cual/current/bin/cual']
client = Client(command)
try:
    tools = client.call('tools/list', {})['tools']
    names = {item['name'] for item in tools}
    assert {'js', 'js_reset', 'js_add_node_module_dir', 'turn_ended'} <= names
    description = next(item['description'] for item in tools if item['name'] == 'js')
    assert 'windowId' in description and 'getApp("Example App")' not in description
    initial = client.js('await cua.getState();')
    assert 'Linux computer use' in text(initial)
    assert 'macOS' not in text(initial) and 'On Windows' not in text(initial)
    for attempt in range(30):
        response = client.js('nodeRepl.write(JSON.stringify(await cua.listWindows({emit:false})));')
        windows = json.loads(text(response))
        targets = {w['title']: w for w in windows if w.get('title') in ('Cual Target', 'Cual Other', 'Cual Fallback')}
        if len(targets) == 3:
            break
        time.sleep(0.1)
    assert len(targets) == 3, windows
    state = text(client.js(f'let app = await cua.getApp({{windowId:{targets["Cual Target"]["id"]}}});'))
    assert 'at_spi' in state, state
    print('Initial accessibility:', state, flush=True)
    # Read actual IDs from the observed accessibility text, not implementation state.
    def element(state, label):
        line = next(line for line in state.splitlines() if label in line)
        match = re.search(r'\[(\d+)\]', line) or re.search(r'^\s*(\d+)\b', line)
        assert match, line
        return match.group(1)
    entry = element(state, 'Draft text')
    expected = 'Café 日本語 🐧'
    state = text(client.js(f'await app.click({json.dumps(entry)}); await app.typeText({json.dumps(expected)}); await app.getAXState();'))
    assert expected in state, state
    button = element(state, 'Save draft')
    saved = text(client.js(f'await app.click({json.dumps(button)}); await app.getAXState();'))
    assert 'Saved: ' + expected in saved, saved
    assert Path(os.environ['CUAL_TEST_OUTPUT'], 'Target.txt').read_text() == expected
    # Native key combinations, text paste, and an advertised secondary action.
    entry = element(saved, 'Draft text')
    expected = 'Second pass Δ'
    state = text(client.js(f'await app.click({json.dumps(entry)}); await app.pressKey("ctrl+a"); await app.paste({json.dumps(expected)}); await app.getAXState();'))
    assert expected in state
    entry, button = element(state, 'Draft text'), element(state, 'Save draft')
    client.js(f'await app.performSecondaryAction({json.dumps(entry)}, "activate"); await app.getAXState();')
    assert Path(os.environ['CUAL_TEST_OUTPUT'], 'Target-activated').read_text() == 'yes'
    client.js(f'await app.click({json.dumps(button)}); await app.getAXState();')
    assert Path(os.environ['CUAL_TEST_OUTPUT'], 'Target.txt').read_text() == expected
    other = text(client.js(f'let other = await cua.getApp({{windowId:{targets["Cual Other"]["id"]}}});'))
    assert 'untouched' in other and expected not in other
    image = client.js('await app.getScreenshot();')
    images = [c for c in image['content'] if c['type'] == 'image']
    assert len(images) == 1 and images[0]['mimeType'] == 'image/jpeg'
    assert len(images[0]['data']) > 1000
    fallback = text(client.js(f'let fallback = await cua.getApp({{windowId:{targets["Cual Fallback"]["id"]}}});'))
    assert 'Accessibility source: x11' in fallback, fallback
    client.js('await fallback.getScreenshot();')
    client.js('await fallback.click([40,40]); await fallback.getAXState();')
    assert Path(os.environ['CUAL_TEST_OUTPUT'], 'fallback-click.txt').read_text() == '40,40'
    client.js('await app.setValue(1, "bad");', error=True)
    client.js('await app.selectText(1, "bad");', error=True)
    client.js('await app.scroll([50,50], "down", 2);', error=True)
    client.js('await cua.getApp("Cual Target");', error=True)
    client.js('await app.click("not-an-element");', error=True)
    # A failed input must not silently write to another window or change the file.
    assert Path(os.environ['CUAL_TEST_OUTPUT'], 'Target.txt').read_text() == expected
    client.js('let persisted = 41;')
    assert text(client.js('nodeRepl.write(persisted + 1);')) == '42'
    client.call('tools/call', {'name': 'js_reset', 'arguments': {}})
    client.js('await cua.listWindows();')
    assert text(client.js('nodeRepl.write(typeof persisted);')) == 'undefined'
    assert 'Linux computer use' in text(client.js('await cua.rewriteDocumentation();'))
    # Timeout and recovery use the original REPL behavior.
    client.js('await new Promise(() => {});', error=True, timeout_ms=100)
    client.js('await cua.listWindows();')
    assert text(client.js('nodeRepl.write(6 * 7);')) == '42'
    print('PASS: MCP discovery, Linux docs, AT-SPI, Unicode, keys, paste, secondary action, window isolation, save oracle, X11 fallback coordinates, JPEG, errors, persistence, reset, timeout recovery')
finally:
    client.close()
