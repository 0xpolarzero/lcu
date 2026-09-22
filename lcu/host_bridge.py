"""Own the original IAB host and forward real Codex network requirements."""
from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path
import re
import selectors
import subprocess
import sys
import time
import uuid

from .app_server import AppServerRequestError, app_server
from .protocol import Listener


def session_id(metadata):
    """Read the same real request identity that the upstream runtime receives."""
    if isinstance(metadata, str):
        metadata = json.loads(metadata)
    turn = metadata.get('x-codex-turn-metadata', {}) if isinstance(metadata, dict) else {}
    if isinstance(turn, str):
        turn = json.loads(turn)
    if not isinstance(turn, dict):
        return None
    # Original browser-service pt(): subagents route under their own thread ID,
    # even though session_id still names the root thread in request metadata.
    if turn.get('thread_source') == 'subagent' and isinstance(turn.get('thread_id'), str):
        return turn['thread_id']
    identity = turn.get('session_id')
    return identity if isinstance(identity, str) else None


class BrowserHost:
    def __init__(self, root, env, identity, *, electron_args=(), app_server_connection=None):
        self.root, self.env, self.identity = Path(root), env, identity
        self.electron_args = electron_args
        # Library hosts can share their parent connection. A private notification
        # subscription fans events out without consuming another caller's replies;
        # the caller retains connection ownership.
        self.parent_connection = app_server_connection
        self.notification_subscription = None
        self.stack = ExitStack()
        self.process = None
        self.buffer = b''
        self.events = []
        self.sessions = set()
        self.protocol_listeners = {}
        self.closed_protocol_requests = set()

    def __enter__(self):
        try:
            self.server = self.parent_connection or self.stack.enter_context(app_server(
                self.env['CODEX_CLI_PATH'], os.getcwd(), self.env))
            self.notification_subscription = self.server.subscribe_notifications()
            user_agent = self.server.initialization['userAgent']
            version = re.search(r'/(\d+\.\d+\.\d+(?:[-+][^\s()]+)?)', user_agent)
            if not version:
                raise ValueError('Codex did not provide a recognizable app-server version.')
            self.version = version[1]
            requirements = self.server('configRequirements/read', {})
            env = {**self.env,
                   'LCU_APPLICATION_PATH': str(self.root / 'host/application'),
                   'LCU_IAB_PROVIDER_PATH': str(self.root / 'host/iab/provider.cjs')}
            data = Path(env.get('XDG_DATA_HOME', Path(env.get('HOME', str(Path.home()))) / '.local/share'))
            profile = Path(env.get('LCU_BROWSER_PROFILE', data / 'lcu/browser-profiles' /
                                  hashlib.sha256(self.identity.encode()).hexdigest()))
            if not profile.is_absolute():
                raise ValueError('LCU browser profile must be an absolute path.')
            profile.mkdir(parents=True, exist_ok=True, mode=0o700)
            self.process = subprocess.Popen(
                [str(self.root / 'host/application/ChatGPT'), *self.electron_args,
                 '--user-data-dir=' + str(profile),
                 str(self.root / 'lcu/host'), '--session-id', self.identity],
                env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE)
            self.selector = selectors.DefaultSelector()
            self.selector.register(self.process.stdout, selectors.EVENT_READ)
            self.stack.callback(self.selector.close)
            self.send({'type': 'requirements', 'appServerVersion': self.version,
                       'configRequirements': requirements})
            self.wait('session', self.identity)
            self.sessions.add(self.identity)
            self.protocol_listeners[self.identity] = Listener(self.identity, self.selector)
            return self
        except BaseException:
            self.close()
            raise

    def send(self, event):
        self.process.stdin.write(json.dumps(event).encode() + b'\n')
        self.process.stdin.flush()

    def poll(self, timeout=0):
        # A tiny bounded poll also checks EOF, which invalidates network policy.
        try:
            message = self.notification_subscription.receive(0.001)
            if message:
                self.on_notification(message)
        except BaseException:
            self.send({'type': 'invalidate'})
            raise
        for listener in self.protocol_listeners.values():
            listener.expire()
        for key, _ in self.selector.select(timeout):
            if key.fileobj is self.process.stdout:
                part = self.process.stdout.read1(65536)
                if not part:
                    raise ValueError('Original IAB host exited unexpectedly.')
                self.buffer += part
            else:
                listener, operation = key.data
                try:
                    if operation == 'accept':
                        listener.accept()
                    else:
                        listener.read(key.fileobj, self.send)
                except (ValueError, OSError):
                    if operation == 'client':
                        listener.finish(key.fileobj, error='Invalid protocol request.')
        while b'\n' in self.buffer:
            line, self.buffer = self.buffer.split(b'\n', 1)
            try:
                event = json.loads(line)
            except (ValueError, UnicodeError):
                print(line.decode(errors='replace'), file=sys.stderr)
                continue
            if isinstance(event, dict) and 'lcuHost' in event:
                if any(listener.complete(event) for listener in self.protocol_listeners.values()):
                    continue
                if event.get('requestId') in self.closed_protocol_requests:
                    self.closed_protocol_requests.discard(event['requestId'])
                    continue
                if event['lcuHost'] == 'error':
                    raise ValueError('Original IAB host: ' + str(event.get('message', event)))
                if event['lcuHost'] == 'nonfatal':
                    print('Original IAB host nonfatal: ' + str(event.get('message', event)), file=sys.stderr)
                    continue
                if event['lcuHost'] == 'session-closed':
                    self.sessions.discard(event.get('sessionId'))
                    listener = self.protocol_listeners.pop(event.get('sessionId'), None)
                    if listener:
                        self.closed_protocol_requests.update(listener.pending)
                        listener.close()
                elif event['lcuHost'] == 'app-server-request':
                    self.app_server_request(event)
                else:
                    self.events.append(event)
            else:
                print(line.decode(errors='replace'), file=sys.stderr)

    def on_notification(self, message):
        if 'method' in message:
            self.send({'type': 'notification', 'notification': message})
        if message.get('method') == 'account/updated':
            self.send({'type': 'invalidate'})
            requirements = self.server('configRequirements/read', {})
            self.send({'type': 'requirements', 'appServerVersion': self.version,
                       'configRequirements': requirements})

    def app_server_request(self, event):
        # Original HB/LBe/HXe account reads and vD desktop settings use this seam.
        # Responses (including tokens) go directly to the private child pipe,
        # never into diagnostics, tool output or an evidence file.
        response = {'type': 'app-server-response', 'requestId': event.get('requestId')}
        method = event.get('method')
        params = event.get('params', {})
        desktop_write = method == 'config/batchWrite' and isinstance(params, dict) and isinstance(params.get('edits'), list) and all(
            isinstance(edit, dict) and isinstance(edit.get('keyPath'), str)
            and re.fullmatch(r'desktop\.[A-Za-z][A-Za-z0-9_-]*', edit['keyPath'])
            for edit in params['edits'])
        if method not in ('getAuthStatus', 'account/read', 'configRequirements/read', 'config/read') and not desktop_write:
            response['error'] = {'message': 'Unsupported browser host app-server method.'}
        else:
            try:
                response['result'] = self.server(method, params)
            except AppServerRequestError as error:
                response['error'] = {'message': str(error)}
            except (ValueError, OSError):
                self.send({'type': 'invalidate'})
                raise
        self.send(response)

    def wait(self, kind, identity, timeout=60, *, request_id=None):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            for event in self.events:
                if event.get('lcuHost') == kind and event.get('sessionId') == identity and (
                        request_id is None or event.get('requestId') == request_id):
                    self.events.remove(event)
                    return event
            self.poll(0.1)
        raise ValueError(f'Original IAB host did not acknowledge {kind}.')

    def register(self, identity):
        if identity and identity not in self.sessions:
            self.send({'type': 'session', 'sessionId': identity})
            self.wait('session', identity)
            self.sessions.add(identity)
            self.protocol_listeners[identity] = Listener(identity, self.selector)

    def deliver_deep_link(self, identity, url):
        """Deliver an explicit callback to an existing owner; never claim login success."""
        return self._owned_command('deep-link', identity, {'url': url})

    def register_app_connect_oauth(self, identity, params):
        """Pass actual initiation parameters to the original pending-state handler."""
        return self._owned_command('oauth-operation', identity, {'operation': 'register', 'params': params})

    def clear_app_connect_oauth(self, identity, params):
        return self._owned_command('oauth-operation', identity, {'operation': 'clear', 'params': params})

    def _owned_command(self, kind, identity, payload):
        if identity not in self.sessions:
            raise ValueError('Host delivery requires an existing owned session.')
        request_id = uuid.uuid4().hex
        self.send({'type': kind, 'requestId': request_id, 'sessionId': identity, **payload})
        return self.wait(kind, identity, request_id=request_id)

    def close(self):
        failure = None
        try:
            if self.process:
                if self.process.poll() is None:
                    try:
                        self.send({'type': 'shutdown'})
                        # Original settings flush through the same private RPC
                        # bridge. Closing stdin or blocking in wait() here would
                        # strand those writes and force an ungraceful shutdown.
                        deadline = time.monotonic() + 15
                        while self.process.poll() is None and time.monotonic() < deadline:
                            try:
                                self.poll(0.05)
                            except ValueError as error:
                                # EOF can be observable just before waitpid sees
                                # exit. Preserve any actual host failure otherwise.
                                if str(error) != 'Original IAB host exited unexpectedly.':
                                    raise
                                self.process.wait(timeout=0.2)
                        self.process.wait(timeout=max(0.01, deadline - time.monotonic()))
                    except (ValueError, OSError, subprocess.TimeoutExpired) as error:
                        failure = error
                        if self.process.poll() is None:
                            self.process.terminate()
                        try:
                            self.process.wait(timeout=10)
                        except subprocess.TimeoutExpired:
                            self.process.kill()
                            self.process.wait(timeout=10)
                self.process.stdout.close()
                self.process.stdin.close()
        finally:
            for listener in self.protocol_listeners.values():
                listener.close()
            self.protocol_listeners.clear()
            if self.notification_subscription:
                self.notification_subscription.close()
                self.notification_subscription = None
            self.stack.close()
        if failure:
            raise ValueError('Original IAB host did not complete graceful shutdown.') from failure

    def __exit__(self, *_):
        self.close()


def serve(root, env, identity):
    if not identity:
        raise ValueError('A real session ID is required for the in-app browser host.')
    with BrowserHost(root, env, identity) as host:
        print(json.dumps({'lcuHost': 'ready', 'sessionId': identity}), flush=True)
        while True:
            host.poll(0.25)


def run_mcp(root, env, command):
    """Forward MCP unchanged; register only identities observed on this channel."""
    identity = session_id(env.get('NODE_REPL_REQUEST_META', '{}'))
    if not identity:
        raise ValueError('Browser host requires session_id in NODE_REPL_REQUEST_META.')
    with BrowserHost(root, env, identity) as host:
        child = subprocess.Popen(command, env=env, stdin=subprocess.PIPE)
        selector = selectors.DefaultSelector()
        selector.register(sys.stdin.buffer, selectors.EVENT_READ)
        os.set_blocking(child.stdin.fileno(), False)
        buffer, pending = b'', b''
        input_closed, input_active, writing = False, True, False
        closing_deadline = None
        try:
            while child.poll() is None:
                host.poll()
                if not pending and b'\n' in buffer:
                    line, buffer = buffer.split(b'\n', 1)
                    try:
                        request = json.loads(line)
                    except (ValueError, UnicodeError):
                        request = {}
                    params = request.get('params', {}) if isinstance(request, dict) else {}
                    meta = params.get('_meta', {}) if isinstance(params, dict) else {}
                    try:
                        current_session = session_id(meta)
                    except (ValueError, TypeError):
                        current_session = None
                    host.register(current_session)
                    pending = line + b'\n'
                if input_closed and not pending and buffer:
                    pending, buffer = buffer, b''
                if pending and not writing:
                    selector.register(child.stdin, selectors.EVENT_WRITE)
                    writing = True
                elif not pending and writing:
                    selector.unregister(child.stdin)
                    writing = False
                # Apply backpressure without blocking live policy monitoring.
                if pending and input_active:
                    selector.unregister(sys.stdin.buffer)
                    input_active = False
                elif not pending and not input_active and not input_closed:
                    selector.register(sys.stdin.buffer, selectors.EVENT_READ)
                    input_active = True
                if input_closed and not pending and not buffer and not child.stdin.closed:
                    child.stdin.close()
                    closing_deadline = time.monotonic() + 30
                if closing_deadline and time.monotonic() >= closing_deadline:
                    raise ValueError('Original MCP runtime did not stop after input closed.')
                for key, _ in selector.select(0.2):
                    if key.fileobj is child.stdin:
                        try:
                            pending = pending[os.write(child.stdin.fileno(), pending):]
                        except BlockingIOError:
                            pass
                    else:
                        data = os.read(sys.stdin.fileno(), 65536)
                        if data:
                            buffer += data
                        else:
                            selector.unregister(sys.stdin.buffer)
                            input_active, input_closed = False, True
            return child.returncode
        finally:
            selector.close()
            if not child.stdin.closed:
                child.stdin.close()
            if child.poll() is None:
                child.terminate()
                try:
                    child.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait(timeout=10)
