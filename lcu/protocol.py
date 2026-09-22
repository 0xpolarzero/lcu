"""Opt-in Linux codex:// handoff to one live original browser owner."""
import base64
import hashlib
import json
import os
from pathlib import Path
import socket
import stat
import struct
import subprocess
import time
import uuid


MAX_URL_BYTES = 16384
MAX_CLIENTS = 8
CLIENT_TIMEOUT = 5
RESPONSE_TIMEOUT = 30
SCHEME = 'x-scheme-handler/codex'


def valid_session_id(value):
    if not isinstance(value, str) or not value or len(value) > 4096 or '\0' in value:
        raise ValueError('A nonempty actual session ID is required.')
    return value


def private_directory():
    base = Path(os.environ.get('XDG_RUNTIME_DIR') or
                Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local/share')))
    if not base.is_absolute():
        raise ValueError('The protocol runtime directory must be absolute.')
    directory = base / 'lcu-deep-links'
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    mode = directory.lstat()
    if not stat.S_ISDIR(mode.st_mode) or mode.st_uid != os.getuid() or mode.st_mode & 0o077:
        raise ValueError('The protocol runtime directory must be private to this account.')
    return directory


def socket_path(identity):
    digest = hashlib.sha256(valid_session_id(identity).encode()).hexdigest()[:32]
    path = private_directory() / (digest + '.sock')
    if len(os.fsencode(path)) > 103:
        raise ValueError('The protocol runtime directory is too long for a Unix socket.')
    return path


class Listener:
    """Nonblocking same-user transport; host_bridge owns all Electron routing."""
    def __init__(self, identity, selector):
        self.identity = valid_session_id(identity)
        self.path = socket_path(identity)
        self.selector = selector
        self.clients = {}
        self.pending = {}
        self.deadlines = {}
        self.bound_inode = None
        try:
            existing = self.path.lstat()
        except FileNotFoundError:
            pass
        else:
            raise ValueError('Protocol socket path is occupied; inspect it before removing a stale socket.')
        self.server = socket.socket(socket.AF_UNIX)
        try:
            self.server.bind(str(self.path))
            bound = self.path.lstat()
            self.bound_inode = (bound.st_dev, bound.st_ino)
            os.chmod(self.path, 0o600)
            self.server.listen(8)
            self.server.setblocking(False)
            selector.register(self.server, 1, (self, 'accept'))
        except BaseException:
            self.server.close()
            self.unlink_owned_path()
            raise

    def unlink_owned_path(self):
        try:
            mode = self.path.lstat()
        except FileNotFoundError:
            return
        if stat.S_ISSOCK(mode.st_mode) and (mode.st_dev, mode.st_ino) == self.bound_inode:
            self.path.unlink()

    def accept(self):
        client, _ = self.server.accept()
        try:
            if len(self.clients) + len(self.pending) >= MAX_CLIENTS:
                client.close()
                return
            if struct.unpack('3i', client.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))[1] != os.getuid():
                raise ValueError('Protocol sender belongs to another account.')
            client.setblocking(False)
            self.clients[client] = b''
            self.deadlines[client] = time.monotonic() + CLIENT_TIMEOUT
            self.selector.register(client, 1, (self, 'client'))
        except BaseException:
            client.close()
            raise

    def read(self, client, send):
        data = client.recv(65536)
        if not data:
            self.drop(client)
            return
        buffer = self.clients[client] + data
        if len(buffer) > MAX_URL_BYTES + 128 or buffer.count(b'\n') > 1:
            self.finish(client, error='Invalid protocol request.')
            return
        if not buffer.endswith(b'\n'):
            self.clients[client] = buffer
            return
        try:
            value = json.loads(buffer)
            url = value['url']
            if not isinstance(url, str) or len(url.encode()) > MAX_URL_BYTES:
                raise ValueError()
        except (ValueError, TypeError, KeyError, UnicodeError):
            self.finish(client, error='Invalid protocol request.')
            return
        request_id = uuid.uuid4().hex
        self.pending[request_id] = client
        self.deadlines[client] = time.monotonic() + RESPONSE_TIMEOUT
        self.selector.unregister(client)
        self.clients.pop(client)
        send({'type': 'deep-link', 'requestId': request_id,
              'sessionId': self.identity, 'url': url})

    def complete(self, event):
        client = self.pending.pop(event.get('requestId'), None)
        if client is None:
            return False
        if event.get('lcuHost') == 'deep-link' and event.get('sessionId') == self.identity:
            self.finish(client, accepted=event.get('accepted') is True)
        else:
            self.finish(client, error='Original owner rejected the callback.')
        return True

    def finish(self, client, *, accepted=False, error=None):
        try:
            client.settimeout(1)
            client.sendall(json.dumps({'accepted': accepted, 'error': error}).encode() + b'\n')
        except OSError:
            pass
        self.drop(client)

    def drop(self, client):
        try:
            self.selector.unregister(client)
        except (KeyError, ValueError):
            pass
        self.clients.pop(client, None)
        self.deadlines.pop(client, None)
        for key, value in list(self.pending.items()):
            if value is client:
                del self.pending[key]
        client.close()

    def expire(self):
        now = time.monotonic()
        for client, deadline in list(self.deadlines.items()):
            if now >= deadline:
                self.finish(client, error='Protocol delivery timed out.')

    def close(self):
        for client in set(self.clients) | set(self.pending.values()):
            self.finish(client, error='Original owner stopped.')
        try:
            self.selector.unregister(self.server)
        except (KeyError, ValueError):
            pass
        self.server.close()
        self.unlink_owned_path()


def deliver(identity, url):
    if not isinstance(url, str) or len(url.encode()) > MAX_URL_BYTES:
        raise ValueError('Invalid protocol URL.')
    with socket.socket(socket.AF_UNIX) as client:
        client.settimeout(35)
        try:
            client.connect(str(socket_path(identity)))
        except (FileNotFoundError, ConnectionRefusedError) as error:
            raise ValueError('No live browser owner exists for this session.') from error
        client.sendall(json.dumps({'url': url}).encode() + b'\n')
        reply = b''
        while not reply.endswith(b'\n'):
            part = client.recv(4096)
            if not part or len(reply) + len(part) > 4096:
                raise ValueError('Protocol owner closed without acknowledgement.')
            reply += part
    result = json.loads(reply)
    if result.get('accepted') is not True:
        raise ValueError(result.get('error') or 'Original queue rejected the callback.')
    return result


def _desktop_quote(value):
    if any(c in value for c in '\r\n'):
        raise ValueError('Invalid desktop command path.')
    return '"' + value.replace('\\', '\\\\').replace('"', '\\"').replace('$', '\\$').replace('`', '\\`').replace('%', '%%') + '"'


def install_handler(root, identity, *, set_default=False):
    """Write a session-specific handler; association changes only on explicit request."""
    valid_session_id(identity)
    launcher = Path(root).resolve() / 'bin/lcu'
    if not launcher.is_file():
        raise ValueError('LCU launcher is missing.')
    data = Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local/share'))
    if not data.is_absolute():
        raise ValueError('XDG_DATA_HOME must be absolute.')
    directory = data / 'applications'
    directory.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(identity.encode()).hexdigest()[:16]
    filename = f'lcu-codex-{digest}.desktop'
    encoded = base64.urlsafe_b64encode(identity.encode()).decode().rstrip('=')
    content = ('[Desktop Entry]\nType=Application\nName=LCU Codex callback (' + digest + ')\n'
               'NoDisplay=true\nTerminal=false\nExec=' + _desktop_quote(str(launcher)) +
               ' browser protocol deliver --session-key ' + encoded + ' %u\n'
               'MimeType=' + SCHEME + ';\n')
    path = directory / filename
    if path.is_symlink():
        raise ValueError('Protocol desktop entry must not be a symlink.')
    path.write_text(content)
    path.chmod(0o600)
    if set_default:
        subprocess.run(['xdg-mime', 'default', filename, SCHEME], check=True)
    return path


def decode_session_key(key):
    try:
        return valid_session_id(base64.urlsafe_b64decode(key + '=' * (-len(key) % 4)).decode())
    except (ValueError, UnicodeError) as error:
        raise ValueError('Invalid protocol session key.') from error
