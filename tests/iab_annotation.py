#!/usr/bin/env python3
"""Run the original annotation editor against a private offline page."""
import json
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
    'name': 'lcu-annotation-fixture', 'version': '0.0.0', 'main': 'fixture.cjs'}))
(overlay / 'lcu/host/fixture.cjs').symlink_to(Path(__file__).with_suffix('.cjs').resolve())

sys.path.insert(0, str(overlay))
from lcu.host_bridge import BrowserHost
from lcu.runtime import environment


class Fixture(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-Type', 'text/html')
        self.end_headers()
        self.wfile.write(b'<!doctype html><title>Annotation fixture</title>'
                         b'<h1>Hello original editor</h1><button>Target</button>')

    def log_message(self, *_):
        pass


server = ThreadingHTTPServer(('127.0.0.1', 9876), Fixture)
threading.Thread(target=server.serve_forever, daemon=True).start()
try:
    env = environment(overlay)
    env['LCU_TEST_ORIGINAL_HOST_MAIN'] = str(release / 'lcu/host/main.cjs')
    with BrowserHost(overlay, env, 'annotation-fixture', electron_args=['--no-sandbox']) as host:
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            host.poll(.05)
            for event in host.events:
                if event['lcuHost'] == 'fixture-failed':
                    raise AssertionError(event)
                if event['lcuHost'] == 'fixture-done':
                    assert event['commentBody'] == 'LCU original comment proof'
                    assert event['markerCount'] == 1
                    print(json.dumps(event))
                    sys.exit(0)
            host.events.clear()
        raise TimeoutError('Original annotation fixture did not finish')
finally:
    server.shutdown()
