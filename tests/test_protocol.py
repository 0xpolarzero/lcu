"""Linux socket lifetime and capacity regressions for the OS handoff adapter."""
import os
from pathlib import Path
import selectors
import socket
import tempfile
import unittest
from unittest.mock import patch

from lcu.protocol import CLIENT_TIMEOUT, Listener, MAX_CLIENTS, socket_path


@unittest.skipUnless(hasattr(socket, 'SO_PEERCRED'), 'Linux peer credentials required')
class ProtocolSocketTest(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.TemporaryDirectory()
        self.addCleanup(self.home.cleanup)
        self.environ = patch.dict(os.environ, {'XDG_RUNTIME_DIR': self.home.name})
        self.environ.start()
        self.addCleanup(self.environ.stop)
        self.selector = selectors.DefaultSelector()
        self.addCleanup(self.selector.close)

    def test_preexisting_refused_socket_is_preserved(self):
        path = socket_path('occupied')
        stale = socket.socket(socket.AF_UNIX)
        stale.bind(str(path))
        stale.close()
        before = path.lstat().st_ino
        with self.assertRaisesRegex(ValueError, 'occupied'):
            Listener('occupied', self.selector)
        self.assertEqual(path.lstat().st_ino, before)

    def test_close_preserves_replacement_path(self):
        listener = Listener('replaced', self.selector)
        path = listener.path
        path.unlink()
        replacement = socket.socket(socket.AF_UNIX)
        replacement.bind(str(path))
        try:
            inode = path.lstat().st_ino
            listener.close()
            self.assertEqual(path.lstat().st_ino, inode)
        finally:
            replacement.close()

    def test_idle_clients_expire_and_capacity_is_bounded(self):
        listener = Listener('capacity', self.selector)
        self.addCleanup(listener.close)
        clients = []
        self.addCleanup(lambda: [client.close() for client in clients])
        for _ in range(MAX_CLIENTS + 1):
            client = socket.socket(socket.AF_UNIX)
            client.connect(str(listener.path))
            clients.append(client)
            listener.accept()
        self.assertEqual(len(listener.clients), MAX_CLIENTS)
        with patch('lcu.protocol.time.monotonic', return_value=10**12):
            listener.expire()
        self.assertFalse(listener.clients)
        self.assertFalse(listener.deadlines)
        self.assertEqual(listener.path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(Path(listener.path).parent.stat().st_mode & 0o777, 0o700)


if __name__ == '__main__':
    unittest.main()
