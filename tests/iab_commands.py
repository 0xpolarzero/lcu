#!/usr/bin/env python3
"""Exercise the installed original browser panel with native Electron input."""
import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

release = Path(sys.argv[1]).resolve()
output = Path(sys.argv[2]).resolve()
output.mkdir(parents=True, exist_ok=True)
overlay = output / 'overlay'
overlay.mkdir()
for entry in release.iterdir():
    if entry.name != 'lcu':
        (overlay / entry.name).symlink_to(entry, target_is_directory=entry.is_dir())
(overlay / 'lcu').mkdir()
for entry in (release / 'lcu').iterdir():
    if entry.name != 'host':
        (overlay / 'lcu' / entry.name).symlink_to(entry, target_is_directory=entry.is_dir())
(overlay / 'lcu/host').mkdir()
for entry in (release / 'lcu/host').iterdir():
    if entry.name != 'package.json':
        (overlay / 'lcu/host' / entry.name).symlink_to(entry, target_is_directory=entry.is_dir())
(overlay / 'lcu/host/package.json').write_text(json.dumps({
    'name': 'lcu-browser-commands-fixture', 'version': '0.0.0', 'main': 'fixture.cjs'}))
(overlay / 'lcu/host/fixture.cjs').symlink_to(Path(__file__).with_suffix('.cjs').resolve())

sys.path.insert(0, str(overlay))
from lcu.host_bridge import BrowserHost
from lcu.runtime import environment


class Fixture(BaseHTTPRequestHandler):
    counts = {'/': 0, '/next': 0}

    def do_GET(self):
        path = self.path.split('?', 1)[0]
        if path not in self.counts:
            self.send_error(404)
            return
        self.counts[path] += 1
        body = (f'<!doctype html><title>{path} command fixture</title>'
                f'<h1 id="path">{path}</h1><p id="loads">{self.counts[path]}</p>'
                '<p>needle needle needle</p>').encode()
        self.send_response(200)
        self.send_header('Content-Type', 'text/html')
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_):
        pass


server = ThreadingHTTPServer(('127.0.0.1', 9877), Fixture)
threading.Thread(target=server.serve_forever, daemon=True).start()
try:
    env = environment(overlay)
    env['LCU_TEST_ORIGINAL_HOST_MAIN'] = os.environ.get('LCU_TEST_HOST_MAIN', str(release / 'lcu/host/main.cjs'))
    with BrowserHost(overlay, env, 'commands-fixture', electron_args=['--no-sandbox']) as host:
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            host.poll(.05)
            for event in host.events:
                if event['lcuHost'] == 'fixture-failed':
                    raise AssertionError(event)
                if event['lcuHost'] == 'fixture-done':
                    print(json.dumps(event))
                    sys.exit(0)
            host.events.clear()
        raise TimeoutError('Original browser command fixture did not finish')
finally:
    server.shutdown()
