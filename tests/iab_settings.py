"""Offline original settings persistence gate; no personal configuration is used."""
import argparse
import json
import os
from pathlib import Path
import selectors
import subprocess
import sys
import time
import tomllib

def run(application, generated, output, release=None):
    library = release or Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(library))
    from lcu.app_server import app_server
    output.mkdir(parents=True)
    home = output / 'home'
    codex_home = home / '.codex'
    codex_home.mkdir(parents=True)
    config = codex_home / 'config.toml'
    config.write_text('approval_policy="never"\nsandbox_mode="read-only"\n[desktop]\nbrowser-download-directory="/fixture-downloads-before"\nbrowser-download-prompt-enabled=true\n')
    (codex_home / 'keybindings.json').write_text('[{"command":"closeTab","key":"Ctrl+Alt+W"}]\n')
    fixture = output / 'app'
    fixture.mkdir()
    (fixture / 'package.json').write_text('{"name":"lcu-settings-fixture","version":"0.0.0","main":"main.cjs"}')
    (fixture / 'main.cjs').write_text('require(' + json.dumps(str(Path(__file__).with_suffix('.cjs'))) + ');\n')
    env = {**os.environ, 'HOME': str(home), 'CODEX_HOME': str(codex_home),
           'LCU_APPLICATION_PATH': str(application), 'LCU_IAB_PROVIDER_PATH': str(generated / 'provider.cjs'),
           'LCU_SETTINGS_MODULE': str(library / 'lcu/host/settings.cjs')}
    trace, summary = [], None
    with app_server(application / 'resources/codex', output, env) as native, (output / 'stderr.log').open('w') as stderr:
        process = subprocess.Popen([str(application / 'ChatGPT'), '--no-sandbox', '--user-data-dir=' + str(output / 'profile'), str(fixture)],
                                   env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=stderr)
        selector = selectors.DefaultSelector()
        selector.register(process.stdout, selectors.EVENT_READ)
        buffer = b''
        try:
            deadline = time.monotonic() + 90
            while time.monotonic() < deadline:
                if not selector.select(.2):
                    if process.poll() is not None:
                        break
                    continue
                chunk = process.stdout.read1(65536)
                if not chunk:
                    break
                buffer += chunk
                while b'\n' in buffer:
                    line, buffer = buffer.split(b'\n', 1)
                    try:
                        event = json.loads(line)
                    except ValueError:
                        continue
                    if 'fixtureRequest' in event:
                        assert event['method'] in ('config/read', 'config/batchWrite'), event
                        if event['method'] == 'config/batchWrite':
                            assert all(edit['keyPath'].startswith('desktop.') and edit['mergeStrategy'] == 'replace' for edit in event['params']['edits']), event
                        trace.append(event)
                        response = native(event['method'], event['params'])
                        process.stdin.write(json.dumps({'id': event['fixtureRequest'], 'result': response}).encode() + b'\n')
                        process.stdin.flush()
                    elif 'fixtureResult' in event:
                        summary = event['fixtureResult']
            process.wait(timeout=10)
            assert process.returncode == 0 and summary, (process.returncode, (output / 'stderr.log').read_text())
        finally:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=10)
            process.stdin.close()
            process.stdout.close()
            selector.close()
    persisted = tomllib.loads(config.read_text())
    assert persisted['approval_policy'] == 'never' and persisted['sandbox_mode'] == 'read-only'
    assert persisted['desktop']['browser-download-directory'] == '/fixture-downloads-after'
    assert persisted['desktop']['browser-download-prompt-enabled'] is False
    assert persisted['desktop']['browser-disabled-site-annotation-hostnames'] == ['example.test']
    assert len(trace) >= 2 and any(item['method'] == 'config/batchWrite' for item in trace)
    (output / 'summary.json').write_text(json.dumps({'checks': summary, 'requests': trace, 'persisted': persisted}, indent=2))
    print('PASS: original desktop settings and keymap read, original validation/change notifications, native CLI persistence and independent TOML outcomes')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('application', type=Path)
    parser.add_argument('generated', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--release', type=Path, help='Import host adapters from this actual candidate release')
    args = parser.parse_args()
    assert {entry.name for entry in Path('/sys/class/net').iterdir()} == {'lo'}, 'Run with --network none'
    run(args.application, args.generated, args.output, args.release)
