#!/usr/bin/env python3
"""Real Linux desktop-handler handoff to the unchanged original dk queue."""
import base64
import json
from pathlib import Path
import subprocess
import sys
import time

root = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(root))
from lcu.host_bridge import BrowserHost
from lcu.protocol import SCHEME, deliver, install_handler, socket_path
from lcu.runtime import environment


def pump(host, process, timeout=35):
    deadline = time.monotonic() + timeout
    while process.poll() is None and time.monotonic() < deadline:
        host.poll(0.05)
    output, error = process.communicate(timeout=2)
    return process.returncode, output, error


def main():
    env = environment(root)
    first, second = 'protocol-fixture-a', 'protocol-fixture-b'
    applications = Path(env['XDG_DATA_HOME']) / 'applications'
    applications.mkdir(parents=True, exist_ok=True)
    (applications / 'existing-codex-handler.desktop').write_text(
        '[Desktop Entry]\nType=Application\nName=Existing callback handler\n'
        'Exec=/bin/true %u\nMimeType=' + SCHEME + ';\n')
    subprocess.run(['xdg-mime', 'default', 'existing-codex-handler.desktop', SCHEME], env=env, check=True)
    desktop = install_handler(root, first)
    assert desktop.is_file()
    # Merely installing must leave the user's pre-existing association intact.
    before = subprocess.run(['xdg-mime', 'query', 'default', SCHEME],
                            capture_output=True, text=True, env=env).stdout.strip()
    assert before == 'existing-codex-handler.desktop', before
    install_handler(root, first, set_default=True)
    selected = subprocess.run(['gio', 'mime', SCHEME],
                              capture_output=True, text=True, env=env, check=True).stdout
    assert desktop.name in selected, selected
    assert str(root / 'bin/lcu') in desktop.read_text()
    callback = 'codex://connector/oauth_callback?code=fixture-a&state=fixture-a'
    other = 'codex://connector/oauth_callback?code=fixture-b&state=fixture-b'
    with BrowserHost(root, env, first, electron_args=['--no-sandbox']) as host:
        assert socket_path(first).is_socket()
        host.register(second)
        assert socket_path(second).is_socket()
        observed = []
        for identity, listener in host.protocol_listeners.items():
            original = listener.complete
            def record(event, identity=identity, original=original, listener=listener):
                if event.get('lcuHost') in ('deep-link', 'error') and event.get('requestId') in listener.pending:
                    observed.append((identity, event.get('lcuHost'), event.get('accepted')))
                return original(event)
            listener.complete = record
        encoded = base64.urlsafe_b64encode(first.encode()).decode().rstrip('=')
        # GIO resolves the selected scheme association and starts its handler.
        # Descendants can retain stdio after gio exits, so do not capture pipes.
        opened = subprocess.Popen(['gio', 'open', other], env=env,
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        deadline = time.monotonic() + 35
        while not observed and time.monotonic() < deadline:
            host.poll(0.05)
            if opened.poll() is not None and opened.returncode != 0:
                break
        if opened.poll() is None:
            opened.terminate()
        opened.wait(timeout=5)
        assert observed, 'GIO did not deliver the selected codex:// handler URL.'
        assert observed == [(first, 'deep-link', True)], observed
        # The second owner's explicit endpoint still receives only its own URL.
        install_handler(root, second)
        child = subprocess.Popen([str(root / 'bin/lcu'), 'browser', 'protocol', 'deliver',
                                  '--session-key', base64.urlsafe_b64encode(second.encode()).decode().rstrip('='), other],
                                 env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        code, _, error = pump(host, child)
        assert code == 0, error
        assert observed[-1] == (second, 'deep-link', True), observed
        # Upstream parser rejects non-callback routes in the owner host.
        invalid = subprocess.Popen([str(root / 'bin/lcu'), 'browser', 'protocol', 'deliver',
                                    '--session-key', encoded, 'codex://launch'],
                                   env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        code, _, error = pump(host, invalid)
        assert code != 0 and 'rejected' in error.lower(), (code, error)
        assert observed[-1][0] == first and observed[-1][1] == 'error', observed
    assert not socket_path(first).exists() and not socket_path(second).exists()
    unavailable = subprocess.run([str(root / 'bin/lcu'), 'browser', 'protocol', 'deliver',
                                  '--session-key', encoded, callback], env=env,
                                 capture_output=True, text=True, timeout=10)
    assert unavailable.returncode != 0 and 'No live browser owner' in unavailable.stderr
    print(json.dumps({'desktop_association_opt_in':'PASS','gio_open_os_invocation':'PASS',
                      'second_invocation_forwarding':'PASS','original_queue_acceptance':'PASS',
                      'two_owner_isolation':'PASS','invalid_route_rejection':'PASS',
                      'owner_shutdown_cleanup':'PASS','missing_owner_failure':'PASS',
                      'authenticated_oauth_completion':'NOT EXERCISED'}))


if __name__ == '__main__':
    main()
