"""Exercise the original Chrome extension through LCU's installed native host."""
import contextlib
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from mcp_client import Client, text

def last_value(result):
    return json.loads(next(item['text'] for item in reversed(result['content']) if item['type'] == 'text'))


def discovery(client):
    observed = []
    for attempt in range(90):
        result = client.js('await cua.listBrowsers();')
        browsers = last_value(result)
        if any(browser['type'] == 'extension' and browser.get('family') == 'chrome' for browser in browsers):
            return browsers
        if not observed or observed[-1] != browsers:
            observed.append(browsers)
        time.sleep(0.5)
    raise AssertionError(f'Original extension/native host did not become discoverable: {observed[-5:]}')


def local_fixture_approval(approvals):
    def handle(method, params):
        if method != 'elicitation/create':
            raise AssertionError(f'Unexpected host request: {method}')
        urls = re.findall(r'https?://[^\s"<>]+', json.dumps(params, sort_keys=True))
        if not urls or any((urlsplit(url).scheme, urlsplit(url).hostname, urlsplit(url).port)
                           != ('http', '127.0.0.1', 8080) for url in urls):
            raise AssertionError(f'Browser approval exceeded the local fixture: {urls}')
        approvals.extend(urls)
        return {'action': 'accept', 'content': {}}
    return handle


PAGE = b'''<!doctype html><title>LCU browser probe</title>
<label for="entry">Message</label><input id="entry">
<button id="save" onclick="fetch('/save?text=' + encodeURIComponent(document.querySelector('#entry').value)).then(() => document.querySelector('#result').textContent = 'Saved')">Save</button>
<output id="result"></output>'''


def fixture_server(requests_seen):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            requests_seen.append((self.path, self.headers.get('x-browser-agent')))
            body = b'ok' if self.path.startswith('/save?') else PAGE
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(('127.0.0.1', 8080), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def browser_actions(client, requests_seen, session_id):
    client.js('let tab = await cua.createBrowserTab("chrome", "http://127.0.0.1:8080/");')
    state = text(client.js('await tab.getAXState();'))
    field = re.search(r'(?m)^\s*(\d+) text field .*ID: entry$', state)
    button = re.search(r'(?m)^\s*(\d+) button Save, ID: save$', state)
    assert field and button, state
    marker = 'LCU hello Åß🙂'
    client.js(f'await tab.typeText({field.group(1)}, {json.dumps(marker)});')
    client.js(f'await tab.click({button.group(1)});')
    for _ in range(10):
        state = text(client.js('await tab.getAXState();'))
        if 'Saved' in state:
            break
        time.sleep(0.1)
    assert 'Saved' in state, state
    assert any(parse_qs(urlsplit(path).query).get('text') == [marker]
               for path, _header in requests_seen if path.startswith('/save?')), requests_seen
    assert requests_seen and all(header == f'ChatGPT/{session_id}'
                                 for _path, header in requests_seen), requests_seen
    screenshot = client.js('await tab.getScreenshot();')
    assert any(item.get('type') == 'image' and len(item.get('data', '')) > 100
               for item in screenshot['content']), screenshot
    client.js('await tab.close();')


def cli_setup_contract(release):
    """Exercise the external Chrome installer boundary without touching a browser."""
    sys.path.insert(0, str(release))
    from lcu.browser import install, main as browser_main

    with tempfile.TemporaryDirectory(prefix='lcu-browser-cli-') as temporary:
        work = Path(temporary)
        root = work / 'release'
        app = work / 'installed-app'
        plugin = app / 'resources/plugins/openai-bundled/plugins/chrome'
        installer = plugin / 'scripts/installManifest.mjs'
        installer.parent.mkdir(parents=True)
        installer.write_text('original installer fixture')
        original_host = plugin / 'extension-host/linux/arm64/extension-host'
        original_host.parent.mkdir(parents=True)
        original_host.write_text('original host fixture')
        root.mkdir()
        (root / 'app').symlink_to(app, target_is_directory=True)
        (root / 'lcu').mkdir()
        shutil.copy2(Path(__file__).resolve().parents[1] / 'lcu/native_host.py',
                     root / 'lcu/native_host.py')
        data = work / 'user-data'
        runtime_env = {'HOME': str(work), 'XDG_CONFIG_HOME': str(work / 'config'),
                       'NODE_REPL_NODE_PATH': '/pinned/node',
                       'CUA_REPL_NODE_REPL_PATH': '/pinned/node_repl',
                       'CODEX_CLI_PATH': '/pinned/codex'}
        expected = data / 'lcu/browser' / hashlib.sha256(str(app.resolve()).encode()).hexdigest()[:16]
        manifest = work / 'config/google-chrome/NativeMessagingHosts/com.openai.codexextension.json'
        manifest.parent.mkdir(parents=True)

        def original_install(command, **_kwargs):
            manifest.write_text(json.dumps({'name': 'com.openai.codexextension',
                'path': str(expected / 'chrome/extension-host/linux/arm64/extension-host'),
                'allowed_origins': ['chrome-extension://hehggadaopoacecdllhhajmbjkdcmajg/']}))
            return subprocess.CompletedProcess(command, 0)

        with patch.dict(os.environ, {'HOME': str(work), 'XDG_DATA_HOME': str(data),
                                      'XDG_CONFIG_HOME': str(work / 'config')}, clear=False), \
                patch('lcu.runtime.environment', return_value=runtime_env), \
                patch('lcu.browser.subprocess.run', side_effect=original_install) as run:
            destination = install(root)
            assert destination == expected
            copied = destination / 'chrome/scripts/installManifest.mjs'
            assert copied.read_text() == installer.read_text()
            assert copied.stat().st_uid == os.getuid(), 'native-host copy must belong to this Linux account'
            assert copied.is_file() and os.access(destination, os.W_OK)
            assert not copied.samefile(installer), 'installer must run from a private copy, never the immutable app'
            relay = destination / 'lcu-native-host'
            assert relay.read_bytes() == (root / 'lcu/native_host.py').read_bytes()
            assert os.access(relay, os.X_OK)
            configured = json.loads(manifest.read_text())
            assert configured['path'] == str(relay)
            assert configured['allowed_origins'] == ['chrome-extension://hehggadaopoacecdllhhajmbjkdcmajg/']
            run.assert_called_once()

            copied.unlink()
            try:
                install(root)
            except ValueError as error:
                assert 'incomplete or corrupt' in str(error)
            else:
                raise AssertionError('corrupt private browser-host copy was accepted')

            foreign = work / 'foreign'
            foreign.mkdir()
            (foreign / '.lcu-browser-host').write_text('/another/release\n')
            try:
                install(root, foreign)
            except ValueError as error:
                assert 'another installation' in str(error)
            else:
                raise AssertionError('foreign browser-host directory was accepted')

        for removed_command in ('serve', 'protocol'):
            stderr = io.StringIO()
            try:
                with contextlib.redirect_stderr(stderr):
                    browser_main(root, [removed_command])
            except SystemExit as error:
                assert error.code == 2
            else:
                raise AssertionError(f'removed `{removed_command}` command was accepted')
            message = stderr.getvalue()
            assert 'were removed' in message and 'lcu browser install' in message, message

    print('PASS: app-symlink Chrome plugin resolution, same-user private host copy, LCU relay manifest, corruption/foreign guards, and IAB migration errors')


from differential_baseline import environment as upstream_environment


def chrome(release, original):
    cli_setup_contract(release)
    base = dict(os.environ)
    base.pop('NODE_REPL_REQUEST_META', None)
    base['CUA_REPL_ENABLED_SURFACES'] = 'browser'
    base['CUA_REPL_BROWSER_ENV'] = 'codex-app'
    base['NODE_REPL_DISABLE_ANALYTICS'] = '1'
    requests_seen = []
    approved_urls = []
    server = fixture_server(requests_seen)
    candidate = Client([str(release / 'bin/lcu')], env=base,
                       request_handler=local_fixture_approval(approved_urls), capabilities={'elicitation': {}})
    try:
        lcu_browsers = discovery(candidate)
        fallback = last_value(candidate.js('nodeRepl.write(JSON.stringify(nodeRepl.requestMeta));'))
        identity = fallback['x-codex-turn-metadata']
        assert set(identity) == {'session_id', 'turn_id'}, identity
        assert identity['session_id'].startswith('lcu-'), identity
        # Discovery should match the untouched service. Its auth decision is
        # tested separately with the original manifest: this Chrome profile
        # currently routes both clients through the installed LCU relay.
        baseline_env = upstream_environment(original, base)
        baseline_env['NODE_REPL_REQUEST_META'] = json.dumps(fallback)
        baseline = Client([str(original / 'bin/node'),
                          str(original / 'lib/node_modules/@oai/cua-repl/bin/cua-repl.mjs')],
                          env=baseline_env, request_handler=local_fixture_approval([]),
                          capabilities={'elicitation': {}})
        try:
            original_browsers = discovery(baseline)
            assert original_browsers == lcu_browsers, (original_browsers, lcu_browsers)
        finally:
            baseline.close()
        host_metadata = {'x-codex-turn-metadata': {'session_id': 'fixture-host-session', 'turn_id': 'fixture-host-turn'}}
        override = candidate.call('tools/call', {'name': 'js', '_meta': host_metadata,
            'arguments': {'code': 'nodeRepl.write(JSON.stringify(nodeRepl.requestMeta));'}})
        assert last_value(override)['x-codex-turn-metadata'] == host_metadata['x-codex-turn-metadata']
        browser_actions(candidate, requests_seen, identity['session_id'])
        assert approved_urls, 'Browser action did not request scoped site approval'
    finally:
        candidate.close()
        server.shutdown()

    print(json.dumps({'discovery': 'PASS: real original extension and native host',
        'generic_mcp_connection_identity': 'PASS', 'caller_metadata_override': 'PASS',
        'original_discovery': 'MATCH',
        'lcu_browser_actions': 'PASS: navigation, Unicode, click, save, screenshot, close, and agent header',
        'approved_urls': approved_urls,
        'agent_header_requests': requests_seen}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    if sys.argv[1:2] == ['--cli-setup-contract']:
        cli_setup_contract(Path(__file__).resolve().parents[1])
    else:
        chrome(*map(Path, sys.argv[1:]))
