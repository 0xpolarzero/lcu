#!/usr/bin/env python3
"""Original permission UI: native clicks and independent HTTP page outcomes."""
import ctypes
import json
import os
from pathlib import Path
import queue
import select
import socket
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.request import urlopen

sys.path.insert(0, str(Path(sys.argv[1]).resolve()))
from lcu.host_bridge import BrowserHost
from lcu.runtime import environment
from iab_host import Pipe


class Fixture(BaseHTTPRequestHandler):
    results = queue.Queue()

    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-Type', 'text/html')
        self.end_headers()
        self.wfile.write(b'''<!doctype html><title>Permission fixture</title>
<button style="margin:80px;padding:30px" onclick="readClipboard()">Read clipboard</button>
<script>async function readClipboard(){let result;try {result={value:await navigator.clipboard.readText()};}
catch(error){result={error:error.name};}await fetch('/result',{method:'POST',body:JSON.stringify(result)});}</script>''')

    def do_POST(self):
        self.results.put(json.loads(self.rfile.read(int(self.headers['Content-Length']))))
        self.send_response(204)
        self.end_headers()

    def log_message(self, *_):
        pass


class EarlyWindowMiss(Exception):
    """The fresh fixture did not leave enough time for a measured early click."""


def native_click(x, y):
    xlib = ctypes.CDLL('libX11.so.6')
    xtest = ctypes.CDLL('libXtst.so.6')
    pointer = ctypes.c_void_p
    xlib.XOpenDisplay.argtypes = [ctypes.c_char_p]
    xlib.XOpenDisplay.restype = pointer
    xlib.XFlush.argtypes = [pointer]
    xlib.XSync.argtypes = [pointer, ctypes.c_int]
    xlib.XCloseDisplay.argtypes = [pointer]
    xlib.XDefaultRootWindow.argtypes = [pointer]
    xlib.XDefaultRootWindow.restype = ctypes.c_ulong
    xlib.XGetInputFocus.argtypes = [pointer, ctypes.POINTER(ctypes.c_ulong), ctypes.POINTER(ctypes.c_int)]
    xlib.XQueryPointer.argtypes = [pointer, ctypes.c_ulong, ctypes.POINTER(ctypes.c_ulong),
        ctypes.POINTER(ctypes.c_ulong), ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int),
        ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_uint)]
    xtest.XTestFakeMotionEvent.argtypes = [pointer, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_ulong]
    xtest.XTestFakeButtonEvent.argtypes = [pointer, ctypes.c_uint, ctypes.c_int, ctypes.c_ulong]
    display = xlib.XOpenDisplay(None)
    assert display
    try:
        focus = ctypes.c_ulong()
        revert = ctypes.c_int()
        assert xlib.XGetInputFocus(display, ctypes.byref(focus), ctypes.byref(revert))
        root = xlib.XDefaultRootWindow(display)
        assert xtest.XTestFakeMotionEvent(display, -1, round(x), round(y), 0)
        xlib.XFlush(display)
        xlib.XSync(display, 0)
        root_return = ctypes.c_ulong()
        child_return = ctypes.c_ulong()
        root_x, root_y, window_x, window_y = (ctypes.c_int() for _ in range(4))
        mask = ctypes.c_uint()
        assert xlib.XQueryPointer(display, root, ctypes.byref(root_return), ctypes.byref(child_return),
            ctypes.byref(root_x), ctypes.byref(root_y), ctypes.byref(window_x), ctypes.byref(window_y),
            ctypes.byref(mask))
        press_ns = time.monotonic_ns()
        for pressed in (1, 0):
            assert xtest.XTestFakeButtonEvent(display, 1, pressed, 0)
        xlib.XFlush(display)
        xlib.XSync(display, 0)
        flush_ns = time.monotonic_ns()
    finally:
        xlib.XCloseDisplay(display)
    return {'pressMonotonicNs': press_ns, 'flushMonotonicNs': flush_ns,
            'inputFocusWindow': focus.value, 'pointerRootChildWindow': child_return.value,
            'pointerRootPosition': [root_x.value, root_y.value]}


class ParentDevTools:
    """Keep one test-only CDP connection to the parent IAB renderer."""

    def __init__(self, root, debug_port):
        targets = json.load(urlopen(f'http://127.0.0.1:{debug_port}/json/list', timeout=5))
        target = next(item for item in targets if item.get('url', '').endswith('/index.html'))
        script = '''const ws=new WebSocket(process.argv[1]);let nextId=1;
ws.onopen=()=>console.log('READY');
ws.onmessage=e=>{const r=JSON.parse(e.data);if(r.id)console.log(JSON.stringify({id:r.id,value:r.result?.result?.value,error:r.error||r.result?.exceptionDetails}));};
process.stdin.setEncoding('utf8');let pending='';process.stdin.on('data',chunk=>{pending+=chunk;let i;while((i=pending.indexOf('\\n'))>=0){const expression=JSON.parse(pending.slice(0,i));pending=pending.slice(i+1);const id=nextId++;ws.send(JSON.stringify({id,method:'Runtime.evaluate',params:{expression,returnByValue:true}}));}});
setTimeout(()=>process.exit(2),60000).unref();'''
        self.process = subprocess.Popen(
            [str(root / 'runtime/bin/node'), '-e', script, target['webSocketDebuggerUrl']],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, bufsize=1)
        ready, _, _ = select.select([self.process.stdout], [], [], 5)
        if not ready or self.process.stdout.readline().strip() != 'READY':
            self.close()
            raise RuntimeError('Could not connect persistent CDP observer to the parent IAB renderer')
        self.next_id = 1

    def evaluate(self, expression):
        request_id = self.next_id
        self.next_id += 1
        self.process.stdin.write(json.dumps(expression) + '\n')
        self.process.stdin.flush()
        ready, _, _ = select.select([self.process.stdout], [], [], 5)
        if not ready:
            raise TimeoutError('Parent IAB renderer CDP evaluation timed out')
        response = json.loads(self.process.stdout.readline())
        assert response['id'] == request_id and not response.get('error'), response
        return response.get('value')

    def close(self):
        if self.process.poll() is None:
            self.process.terminate()
            self.process.wait(timeout=5)


def exercise(root, output, decision, attempt):
    home = output / decision / f'attempt-{attempt}' / 'home'
    (home / '.codex').mkdir(parents=True)
    env = {**environment(root), 'HOME': str(home), 'CODEX_HOME': str(home / '.codex')}
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0))
        debug_port = probe.getsockname()[1]
    handler = type(f'FixtureAttempt{attempt}', (Fixture,), {'results': queue.Queue()})
    server = ThreadingHTTPServer(('127.0.0.1', 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    parent_cdp = None
    try:
        with BrowserHost(root, env, 'permission-' + decision,
                         electron_args=['--no-sandbox', '--remote-debugging-port=' + str(debug_port)]) as host:
            paths = list(Path('/tmp/codex-browser-use').glob('*.sock'))
            assert len(paths) == 1, paths
            client = Pipe(paths[0], host)
            meta = {'session_id': 'permission-' + decision, 'turn_id': 'permission-turn'}
            tab = client.call('createTab', meta)

            def cdp(method, params=None):
                return client.call('executeCdp', {**meta, 'target': {'tabId': tab['id']},
                    'method': method, 'commandParams': params or {}})

            cdp('Page.enable')
            cdp('Page.navigate', {'url': f'http://127.0.0.1:{server.server_port}/'})
            client.call('executeUnhandledCommand', {**meta, 'type': 'browser_visibility_set', 'browser_id': 'iab', 'visible': True})
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                ready = cdp('Runtime.evaluate', {'expression': "document.readyState==='complete'&&!!document.querySelector('button')", 'returnByValue': True})
                if ready['result'].get('value'):
                    break
                time.sleep(.1)
            assert ready['result'].get('value'), ready
            parent_cdp = ParentDevTools(root, debug_port)
            geometry = parent_cdp.evaluate(
                '''(()=>{window.__fixturePromptSeen=null;window.__fixturePromptClick=null;
document.addEventListener('click',e=>{let b=e.target.closest('button');if(b&&['Allow','Block','Deny',"Don't allow",'Allow this time'].includes(b.innerText.trim()))window.__fixturePromptClick={trusted:e.isTrusted,button:b.innerText.trim(),eventTimeMs:performance.now()-window.__fixturePromptSeen,performanceNow:performance.now()};},true);
new MutationObserver(()=>{
if(window.__fixturePromptSeen===null&&[...document.querySelectorAll('button')].some(e=>e.innerText==='Allow'))window.__fixturePromptSeen=performance.now();
}).observe(document.body,{subtree:true,childList:true});
return {x:screenX,y:screenY+outerHeight-innerHeight,html:document.body.innerText,
webviews:[...document.querySelectorAll('webview')].map(e=>{let r=e.getBoundingClientRect();return {x:r.x,y:r.y,width:r.width,height:r.height};})};})()''')
            button = cdp('Runtime.evaluate', {'expression': '(()=>{let r=document.querySelector("button").getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2};})()', 'returnByValue': True})['result']['value']
            assert len(geometry['webviews']) == 1, geometry
            hit = parent_cdp.evaluate(
                f'''document.elementFromPoint({geometry['webviews'][0]['x']+button['x']},{geometry['webviews'][0]['y']+button['y']})?.tagName''')
            assert hit == 'WEBVIEW', ('Original page is covered at native click target', hit, geometry)
            native_click(geometry['x'] + geometry['webviews'][0]['x'] + button['x'],
                         geometry['y'] + geometry['webviews'][0]['y'] + button['y'])
            deadline = time.monotonic() + 12
            prompts = []
            names = ('Allow', 'Allow this time') if decision == 'allow' else ('Block', 'Deny', "Don't allow")
            selected = None
            prompt_query_started_ns = None
            while time.monotonic() < deadline:
                host.poll(.05)
                prompt_query_started_ns = time.monotonic_ns()
                prompts = parent_cdp.evaluate(
                    '[...document.querySelectorAll("button")].map(e=>{let r=e.getBoundingClientRect();return {text:e.innerText,x:screenX+r.x+r.width/2,y:screenY+outerHeight-innerHeight+r.y+r.height/2,ageMs:window.__fixturePromptSeen===null?null:performance.now()-window.__fixturePromptSeen};})')
                selected = next((item for item in prompts if item['text'].strip() in names), None)
                if selected:
                    break
                time.sleep(.1)
            assert selected, ('No original permission UI', geometry, prompts,
                              list(handler.results.queue))
            print('ORIGINAL PERMISSION BUTTONS', prompts, flush=True)
            # The query's start time gives a conservative upper bound: the
            # prompt could have been observed at any point after the request
            # began. Include the native event and XFlush before claiming it
            # landed inside the original 500 ms guard. XSync waits for the
            # X server to process the queued XTest input before the timestamp.
            age_at_click_upper_ms = None if selected['ageMs'] is None else selected['ageMs'] + (
                time.monotonic_ns() - prompt_query_started_ns) / 1_000_000
            if age_at_click_upper_ms is None or age_at_click_upper_ms >= 500:
                raise EarlyWindowMiss({
                    'decision': decision,
                    'promptAgeMs': selected['ageMs'],
                    'ageAtClickUpperBoundMs': age_at_click_upper_ms,
                })
            hit = parent_cdp.evaluate(
                f'''(()=>{{let e=document.elementFromPoint({selected['x']-geometry['x']},{selected['y']-geometry['y']});return {{tag:e?.tagName,button:e?.closest('button')?.innerText.trim()}};}})()''')
            assert hit['button'] == selected['text'].strip(), ('Native click target is not the original permission button', hit, selected)
            click_timing = native_click(selected['x'], selected['y'])
            age_at_flush_upper_ms = selected['ageMs'] + (
                click_timing['flushMonotonicNs'] - prompt_query_started_ns) / 1_000_000
            click_observation = None
            if age_at_flush_upper_ms >= 500:
                raise EarlyWindowMiss({
                    'decision': decision,
                    'promptAgeMs': selected['ageMs'],
                    'ageAtClickUpperBoundMs': age_at_flush_upper_ms,
                    'rendererClick': click_observation,
                    **click_timing,
                })
            dispatch_deadline = time.monotonic() + .25
            while time.monotonic() < dispatch_deadline and click_observation is None:
                host.poll(.02)
                click_observation = parent_cdp.evaluate('window.__fixturePromptClick')
            if click_observation is None:
                raise AssertionError('Native early click produced no captured permission-button DOM event')
            if not click_observation.get('trusted') or click_observation['eventTimeMs'] >= 500:
                raise EarlyWindowMiss({
                    'decision': decision,
                    'promptAgeMs': selected['ageMs'],
                    'ageAtClickUpperBoundMs': age_at_flush_upper_ms,
                    'rendererClick': click_observation,
                    **click_timing,
                })
            host.poll(.1)
            assert handler.results.empty(), 'Original early-click guard was bypassed'
            remains = parent_cdp.evaluate(
                '[...document.querySelectorAll("button")].some(e=>e.innerText==="Allow")')
            assert remains, 'Early click unexpectedly resolved the original prompt'
            stable = time.monotonic() + .8
            while time.monotonic() < stable:
                host.poll(.05)
            native_click(selected['x'], selected['y'])
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                host.poll(.05)
                try:
                    result = handler.results.get_nowait()
                    break
                except queue.Empty:
                    time.sleep(.05)
            else:
                raise AssertionError('Page did not report a permission outcome')
            expected = {'value': 'lcu-original-permission-fixture'} if decision == 'allow' else {'error': 'NotAllowedError'}
            assert result == expected, (decision, result)
            client.socket.close()
            return {'decision': decision, 'originalPromptButtons': prompts,
                    'earlyClickGuard': 'PASS',
                    'promptAgeAtNativeClickUpperBoundMs': age_at_flush_upper_ms,
                    'nativeClickTarget': hit,
                    'rendererClick': click_observation,
                    'nativeClickTiming': click_timing,
                    'independentHttpOutcome': result}
    finally:
        if parent_cdp is not None:
            parent_cdp.close()
        server.shutdown()


def main():
    root, output = map(Path, sys.argv[1:])
    output.mkdir(parents=True)
    assert {entry.name for entry in Path('/sys/class/net').iterdir()} == {'lo'}, 'Run with --network none'
    clipboard = subprocess.Popen(['python3', '-u', '-c', '''import gi
gi.require_version('Gtk','3.0')
from gi.repository import Gtk,Gdk
clipboard=Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
clipboard.set_text('lcu-original-permission-fixture',-1)
print('ready',flush=True)
Gtk.main()'''], stdout=subprocess.PIPE)
    try:
        assert clipboard.stdout.readline().strip() == b'ready'
        outcomes = []
        for decision in ('allow', 'deny'):
            misses = []
            for attempt in range(1, 4):
                try:
                    outcome = exercise(root, output, decision, attempt)
                    outcome['missedFreshFixtures'] = misses
                    outcomes.append(outcome)
                    break
                except EarlyWindowMiss as miss:
                    misses.append({'attempt': attempt, **miss.args[0]})
            else:
                raise AssertionError(f'No fresh {decision} fixture produced a measured click within 500 ms: {misses}')
        (output / 'summary.json').write_text(json.dumps(outcomes, indent=2) + '\n')
        print('PASS: original permission prompt, native Xlib clicks, independent clipboard allow/deny outcomes')
    finally:
        clipboard.terminate()
        clipboard.wait(timeout=10)


if __name__ == '__main__':
    main()
