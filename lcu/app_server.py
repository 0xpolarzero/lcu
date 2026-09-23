"""Small stdio adapter to the bundled original Codex app-server."""
from contextlib import contextmanager
import json
import selectors
import subprocess
import tempfile
import threading
import time


class AppServerRequestError(ValueError):
    """An original RPC error, distinct from losing the host connection."""


class NotificationSubscription:
    """A private notification view; reading it never consumes RPC replies."""

    def __init__(self, server):
        self.server = server
        self.messages = []
        self.closed = False

    def receive(self, timeout=0):
        return self.server._receive_notification(self, timeout)

    def close(self):
        self.server._unsubscribe(self)


class AppServer:
    def __init__(self, process, request_handler=None):
        self.process = process
        # The embedding caller owns policy for server-originated requests.
        # A handler receives the complete request and returns a JSON-RPC
        # response envelope carrying that same id and either result or error.
        self.request_handler = request_handler
        self.sequence = 0
        self.buffer = b''
        self._responses = {}
        self._pending = set()
        self._subscriptions = set()
        self._state_lock = threading.Lock()
        self._reader_lock = threading.Lock()
        self._sequence_lock = threading.Lock()
        self._write_lock = threading.Lock()
        self.selector = selectors.DefaultSelector()
        self.selector.register(process.stdout, selectors.EVENT_READ)
        try:
            self.initialization = self('initialize', {
                'clientInfo': {'name': 'lcu', 'version': '0.3.0'},
                'capabilities': {'experimentalApi': True}})
            self.send({'method': 'initialized'})
        except BaseException:
            self.selector.close()
            raise

    def send(self, message):
        with self._write_lock:
            self.process.stdin.write(json.dumps(message).encode() + b'\n')
            self.process.stdin.flush()

    def _read_one(self, timeout):
        deadline = time.monotonic() + timeout
        # The RPC and subscription readers call this in short slices so another
        # waiter can acquire the stream after each bounded selector wait.
        with self._reader_lock:
            while b'\n' not in self.buffer:
                remaining = deadline - time.monotonic()
                if remaining <= 0 or not self.selector.select(min(remaining, 0.05)):
                    if time.monotonic() >= deadline:
                        return None
                    continue
                part = self.process.stdout.read1(65536)
                if not part:
                    raise ValueError('Bundled Codex app-server exited unexpectedly.')
                self.buffer += part
            line, self.buffer = self.buffer.split(b'\n', 1)
        return json.loads(line)

    def _answer_request(self, request):
        request_id = request['id']
        if self.request_handler is None:
            response = {'id': request_id, 'error': {
                'code': -32601, 'message': 'Server-originated requests are unsupported.'}}
        else:
            # No stream, state, or write lock is held here. Handlers may make
            # nested RPC calls on this same connection.
            response = self.request_handler(request)
            if (not isinstance(response, dict) or response.get('id') != request_id or
                    'method' in response or
                    (('result' in response) == ('error' in response))):
                raise ValueError('App-server request handler returned an invalid response envelope.')
        self.send(response)

    def _route(self, message):
        if 'id' in message and 'method' in message:
            self._answer_request(message)
            return
        with self._state_lock:
            if 'id' in message:
                if message['id'] in self._pending:
                    self._responses[message['id']] = message
            else:
                for subscription in self._subscriptions:
                    subscription.messages.append(message)

    def receive(self, timeout):
        """Receive the next wire message, preserving the historical API."""
        message = self._read_one(timeout)
        if message is not None:
            self._route(message)
        return message

    def subscribe_notifications(self):
        subscription = NotificationSubscription(self)
        with self._state_lock:
            self._subscriptions.add(subscription)
        return subscription

    def _unsubscribe(self, subscription):
        with self._state_lock:
            self._subscriptions.discard(subscription)
            subscription.closed = True
            subscription.messages.clear()

    def _receive_notification(self, subscription, timeout):
        deadline = time.monotonic() + timeout
        while True:
            with self._state_lock:
                if subscription.closed:
                    return None
                if subscription.messages:
                    return subscription.messages.pop(0)
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return None
            # Release stream-reader ownership regularly so an RPC waiter can
            # route its reply even while this subscriber is waiting quietly.
            message = self._read_one(min(remaining, 0.05))
            if message is None:
                return None
            self._route(message)

    def __call__(self, method, params, timeout=45):
        with self._sequence_lock:
            self.sequence += 1
            request_id = self.sequence
        with self._state_lock:
            self._pending.add(request_id)
        try:
            self.send({'id': request_id, 'method': method, 'params': params})
            deadline = time.monotonic() + timeout
            while (remaining := deadline - time.monotonic()) > 0:
                with self._state_lock:
                    message = self._responses.pop(request_id, None)
                if message is not None:
                    if 'error' in message:
                        raise AppServerRequestError(message['error']['message'])
                    return message['result']
                message = self._read_one(min(remaining, 0.05))
                if message is None:
                    continue
                self._route(message)
            raise ValueError(f'Bundled Codex app-server timed out: {method}')
        finally:
            with self._state_lock:
                self._pending.discard(request_id)
                self._responses.pop(request_id, None)


@contextmanager
def app_server(cli, cwd, env):
    """Retain caller configuration; never execute a model turn or change policy."""
    with tempfile.TemporaryFile() as errors:
        process = subprocess.Popen(
            [str(cli), '--strict-config', 'app-server', '--listen', 'stdio://'],
            cwd=cwd, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=errors)
        client = None
        try:
            client = AppServer(process)
            yield client
        finally:
            process.stdin.close()
            if process.poll() is None:
                process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)
            if client:
                client.selector.close()
            process.stdout.close()
