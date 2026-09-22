"""Actual MCP navigation against the original IAB, without credentials or bypasses."""
import json
import os
from pathlib import Path
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

release, original, output = map(Path, sys.argv[1:4])
sys.path.insert(0, str(release))
from lcu.host_bridge import BrowserHost
from lcu.runtime import environment
from differential_baseline import environment as upstream_environment
from iab_host import Pipe
from mcp_client import Client, text

observed = set()
received = {side: threading.Event() for side in ('upstream', 'lcu')}
class Page(BaseHTTPRequestHandler):
    def do_GET(self):
        observed.add(self.path)
        if self.path.lstrip('/') in received:
            received[self.path.lstrip('/')].set()
        self.send_response(200)
        self.send_header('Content-Type', 'text/html')
        self.end_headers()
        self.wfile.write(b'<!doctype html><title>Independent IAB navigation outcome</title>Fixture page')
    def log_message(self, *_): pass

server = ThreadingHTTPServer(('127.0.0.1', 0), Page)
threading.Thread(target=server.serve_forever, daemon=True).start()
identity = {'session_id': 'iab-action-fixture', 'turn_id': 'action-turn'}
caller = {**os.environ, 'CUA_REPL_ENABLED_SURFACES': 'browser',
          'CUA_REPL_BROWSER_ENV': 'codex-app', 'BROWSER_USE_AVAILABLE_BACKENDS': 'iab',
          'NODE_REPL_REQUEST_META': json.dumps({'x-codex-turn-metadata': identity})}
results = {}

def permission_check_failure(url):
    """The exact fail-closed upstream diagnostic observed in the offline run."""
    origin = f'{urlsplit(url).scheme}://{urlsplit(url).netloc}'
    return (
        'Browser Use could not complete this action because a browser security check was unavailable. '
        'Reason: The permission request could not complete, so access was not granted. '
        f'Auto-review could not complete for {origin}. '
        'Browser Use is failing closed; no explicit denial was made. This failure may be temporary. '
        'The agent may retry after the issue is resolved, but must not bypass browser security controls '
        'or use an indirect workaround.'
    )

try:
    with BrowserHost(release, environment(release), identity['session_id'], electron_args=['--no-sandbox']) as host:
        host.send({'type': 'session', 'sessionId': identity['session_id']})
        registration = host.wait('session', identity['session_id'])
        pipe = Pipe(registration['pipePath'], host)
        tab = pipe.call('createTab', identity)
        stopped, failures = threading.Event(), []
        def pump():
            try:
                while not stopped.wait(.01): host.poll()
            except BaseException as error: failures.append(error)
        monitor = threading.Thread(target=pump)
        monitor.start()
        try:
            for side in ('upstream', 'lcu'):
                command = ([str(original / 'bin/node'), str(original / 'lib/node_modules/@oai/cua-repl/bin/cua-repl.mjs')]
                           if side == 'upstream' else [str(release / 'bin/lcu')])
                client = Client(command, env=upstream_environment(original, caller) if side == 'upstream' else caller)
                try:
                    client.js("let browser = await cua.getBrowser('iab');")
                    client.js('let tab = await browser.tabs.get(' + json.dumps(str(tab['id'])) + ');')
                    url = f'http://127.0.0.1:{server.server_port}/{side}'
                    result = client.call('tools/call', {'name': 'js', 'arguments': {'code': 'await tab.goto(' + json.dumps(url) + ');'}})
                    if result.get('isError'):
                        diagnostic = text(result)
                        if diagnostic == 'Codex auth token is unavailable':
                            boundary = 'auth_token_unavailable'
                            outcome = 'BLOCKED: original authentication required'
                        elif diagnostic == permission_check_failure(url):
                            boundary = 'permission_check_unavailable_fail_closed'
                            outcome = 'BLOCKED: auto-review permission check unavailable; browser failed closed'
                        else:
                            raise AssertionError(f'Unexpected {side} navigation failure: {result}')
                        assert not received[side].wait(.2), observed
                        results[side] = {'navigation': outcome, 'boundary': boundary,
                                         'diagnostic': diagnostic, 'request_received': False}
                    else:
                        assert received[side].wait(10), (side, observed)
                        results[side] = {'navigation': 'PASS: independent HTTP request observed',
                                         'boundary': 'http_request_observed', 'request_received': True}
                finally:
                    client.close()
                output.write_text(json.dumps(results, indent=2) + '\n')
        finally:
            stopped.set()
            monitor.join(timeout=10)
            pipe.socket.close()
        assert not monitor.is_alive(), 'IAB policy monitor did not stop'
        if failures: raise failures[0]
    assert results['upstream'] == results['lcu'], results
    print(json.dumps(results, indent=2))
finally:
    server.shutdown()
    server.server_close()
