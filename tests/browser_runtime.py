"""Real extension/native-host fidelity; auth failures are blockers, not action passes."""
import json
import os
from pathlib import Path
import sys
import time
import threading

from mcp_client import Client, text

def last_value(result):
    return json.loads(next(item['text'] for item in reversed(result['content']) if item['type'] == 'text'))


def discovery(client):
    for attempt in range(30):
        result = client.js('await cua.listBrowsers();')
        browsers = last_value(result)
        if any(browser['type'] == 'extension' and browser.get('family') == 'chrome' for browser in browsers):
            return browsers
        time.sleep(0.2)
    raise AssertionError('Original extension/native host did not become discoverable')


def attempt_tab(client):
    result = client.call('tools/call', {'name': 'js', 'arguments': {
        'code': 'let tab = await cua.createBrowserTab("chrome", "http://127.0.0.1:8080/");'}})
    # A fresh, offline fixture has no Codex login. Do not silently inject a token,
    # change security policy, or call a matching failure an action-success test.
    if not result.get('isError'):
        raise AssertionError('No-auth boundary changed; inspect before changing this test')
    message = text(result)
    if 'Codex auth token is unavailable' not in message:
        raise AssertionError(f'Unexpected browser action failure: {message}')
    return message


from differential_baseline import environment as upstream_environment


def chrome(release, original):
    base = dict(os.environ)
    base.pop('NODE_REPL_REQUEST_META', None)
    base['CUA_REPL_ENABLED_SURFACES'] = 'browser'
    base['CUA_REPL_BROWSER_ENV'] = 'codex-app'
    base['NODE_REPL_DISABLE_ANALYTICS'] = '1'
    candidate = Client([str(release / 'bin/lcu')], env=base)
    try:
        lcu_browsers = discovery(candidate)
        fallback = last_value(candidate.js('nodeRepl.write(JSON.stringify(nodeRepl.requestMeta));'))
        identity = fallback['x-codex-turn-metadata']
        assert set(identity) == {'session_id', 'turn_id'}, identity
        assert identity['session_id'].startswith('lcu-'), identity
        lcu_error = attempt_tab(candidate)
        host_metadata = {'x-codex-turn-metadata': {'session_id': 'fixture-host-session', 'turn_id': 'fixture-host-turn'}}
        override = candidate.call('tools/call', {'name': 'js', '_meta': host_metadata,
            'arguments': {'code': 'nodeRepl.write(JSON.stringify(nodeRepl.requestMeta));'}})
        assert last_value(override)['x-codex-turn-metadata'] == host_metadata['x-codex-turn-metadata']
    finally:
        candidate.close()

    baseline_env = upstream_environment(original, base)
    baseline_env['NODE_REPL_REQUEST_META'] = json.dumps(fallback)
    baseline = Client([str(original / 'bin/node'),
                      str(original / 'lib/node_modules/@oai/cua-repl/bin/cua-repl.mjs')], env=baseline_env)
    try:
        original_browsers = discovery(baseline)
        assert original_browsers == lcu_browsers, (original_browsers, lcu_browsers)
        assert attempt_tab(baseline) == lcu_error
    finally:
        baseline.close()

    print(json.dumps({'discovery': 'PASS: real original extension and native host',
        'generic_mcp_connection_identity': 'PASS', 'caller_metadata_override': 'PASS',
        'original_vs_lcu_default_auth_boundary': 'MATCH',
        'browser_actions': 'BLOCKED: Codex authentication is required; no browser task-success claim'}, indent=2))


def iab_configurations(release, original, output):
    """Compare actual effective APIs against one real, unchanged IAB provider.

    The provider fixture seeds a real tab through its original native pipe.
    Neither client gains an auth token or bypass. This tests discovery, effective
    API/capability delivery and rejection paths, not authenticated navigation.
    """
    sys.path.insert(0, str(release))
    from lcu.host_bridge import BrowserHost
    from lcu.runtime import environment
    from iab_host import Pipe

    base = dict(os.environ)
    # Let each launcher supply its own defaults, rather than feeding LCU's
    # environment back into the independently assembled original baseline.
    for key in ('BROWSER_USE_TINYSKY_ENABLED', 'BROWSER_USE_CODEX_APP_VERSION',
                'BROWSER_USE_CODEX_APP_BUILD_FLAVOR', 'BUILD_FLAVOR',
                'BROWSER_USE_DISABLE_API_MEMBERS', 'BROWSER_USE_DISABLE_BROWSER_CAPABILITIES',
                'BROWSER_USE_DISABLE_TAB_CAPABILITIES', 'NODE_REPL_NATIVE_PIPE_CONNECT_TIMEOUT_MS'):
        base.pop(key, None)
    base.update(CUA_REPL_ENABLED_SURFACES='browser', CUA_REPL_BROWSER_ENV='codex-app',
                BROWSER_USE_AVAILABLE_BACKENDS='iab', NODE_REPL_DISABLE_ANALYTICS='1',
                NODE_REPL_REQUEST_META=json.dumps({'x-codex-turn-metadata': {
                    'session_id': 'config-fixture', 'turn_id': 'turn-1'}}))
    scenarios = {
        'desktop-default': {},
        'tinysky-off': {'BROWSER_USE_TINYSKY_ENABLED': '0'},
        'api-exclusions': {'BROWSER_USE_DISABLE_API_MEMBERS': ' Tab.playwright , Tab.clipboard '},
        'capability-exclusions': {'BROWSER_USE_DISABLE_BROWSER_CAPABILITIES': ' visibility ',
                                 'BROWSER_USE_DISABLE_TAB_CAPABILITIES': ' pageAssets '},
        'backend-excluded': {'BROWSER_USE_AVAILABLE_BACKENDS': 'chrome'},
        'flavor-mismatch': {'BROWSER_USE_CODEX_APP_BUILD_FLAVOR': 'nightly'},
        'session-mismatch': {'NODE_REPL_REQUEST_META': json.dumps({'x-codex-turn-metadata': {
            'session_id': 'foreign-fixture', 'turn_id': 'turn-1'}})},
    }
    results = {side: {} for side in ('upstream', 'lcu')}
    commands = {
        'upstream': [str(original / 'bin/node'), str(original / 'lib/node_modules/@oai/cua-repl/bin/cua-repl.mjs')],
        'lcu': [str(release / 'bin/lcu')],
    }
    with BrowserHost(release, environment(release), 'config-fixture', electron_args=['--no-sandbox']) as host:
        host.send({'type': 'session', 'sessionId': 'config-fixture'})
        registration = host.wait('session', 'config-fixture')
        pipe = Pipe(registration['pipePath'], host)
        tab = pipe.call('createTab', {'session_id': 'config-fixture', 'turn_id': 'turn-1'})
        # All application creation occurs above via the original provider. The
        # browser clients below only discover and inspect the effective API.
        stopped = threading.Event()
        failures = []
        def pump():
            try:
                while not stopped.wait(.01):
                    host.poll()
            except BaseException as error:
                failures.append(error)
        monitor = threading.Thread(target=pump)
        monitor.start()
        try:
            for side, command in commands.items():
                for scenario, overrides in scenarios.items():
                    caller = {**base, **overrides}
                    env = upstream_environment(original, caller) if side == 'upstream' else caller
                    client = Client(command, env=env)
                    try:
                        selected = client.call('tools/call', {'name': 'js', 'arguments': {
                            'code': "let browser = await cua.getBrowser('iab');"}})
                        if scenario in ('backend-excluded', 'flavor-mismatch', 'session-mismatch'):
                            assert selected.get('isError'), (side, scenario, selected)
                            results[side][scenario] = {'rejection': text(selected)}
                            continue
                        assert not selected.get('isError'), (side, scenario, selected)
                        client.js('let tab = await browser.tabs.get(' + json.dumps(str(tab['id'])) + ');')
                        api = last_value(client.js('nodeRepl.write(JSON.stringify({'
                            'ax:typeof tab.ax,cua:typeof tab.cua,dom:typeof tab.dom_cua,'
                            'playwright:typeof tab.playwright,clipboard:typeof tab.clipboard,'
                            'browserCapabilities:(await browser.capabilities.list()).map(x=>x.id).sort(),'
                            'tabCapabilities:(await tab.capabilities.list()).map(x=>x.id).sort()}));'))
                        if scenario == 'tinysky-off':
                            assert (api['ax'], api['cua'], api['dom']) == ('undefined', 'object', 'object'), api
                            # Current unified getTab assumes ax even with Tinysky
                            # disabled. Record that original failure; never call
                            # it successful alternative-configuration operation.
                            failure = client.js('await cua.getTab(' + json.dumps(str(tab['id'])) + ", {browser:'iab'});", error=True)
                            api['unifiedGetTabFailure'] = text(failure)
                            assert "Cannot read properties of undefined (reading 'get')" in api['unifiedGetTabFailure']
                        else:
                            assert (api['ax'], api['cua'], api['dom']) == ('object', 'undefined', 'undefined'), api
                        expected_api = 'undefined' if scenario == 'api-exclusions' else 'object'
                        assert api['playwright'] == api['clipboard'] == expected_api, api
                        assert ('visibility' in api['browserCapabilities']) == (scenario != 'capability-exclusions'), api
                        assert ('pageAssets' in api['tabCapabilities']) == (scenario != 'capability-exclusions'), api
                        assert 'viewport' in api['browserCapabilities'], api
                        if scenario == 'capability-exclusions':
                            api['browserCapabilityRejection'] = text(client.js(
                                "await browser.capabilities.get('visibility');", error=True))
                            api['tabCapabilityRejection'] = text(client.js(
                                "await tab.capabilities.get('pageAssets');", error=True))
                        results[side][scenario] = api
                    finally:
                        client.close()
                        Path(output).write_text(json.dumps(results, indent=2) + '\n')
        finally:
            stopped.set()
            monitor.join(timeout=10)
            pipe.socket.close()
        assert not monitor.is_alive(), 'Host monitor did not stop'
        if failures:
            raise failures[0]
    assert results['upstream'] == results['lcu'], results
    print(json.dumps({'effective_api_configurations': len(scenarios), 'original_vs_lcu': 'MATCH',
        'provider': 'real original IAB with actual owned tab',
        'original_tinysky_off_unified_getTab_failure': 'MATCH; alternative getter remains broken upstream',
        'scope': 'API, capability and discovery restrictions; no authenticated task-success claim'}, indent=2))


if __name__ == '__main__':
    if sys.argv[1:2] == ['--iab-configurations']:
        iab_configurations(Path(sys.argv[2]), Path(sys.argv[3]), Path(sys.argv[4]))
    else:
        chrome(*map(Path, sys.argv[1:]))
