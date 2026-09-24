"""Pinned Windows host extraction from a disposable ASAR fixture."""

import hashlib
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

from lcu import windows_host


def _asar(path: Path, members: dict[str, bytes]):
    files = {}
    payload = bytearray()
    for name, content in members.items():
        node = files
        parts = name.split('/')
        for part in parts[:-1]:
            node = node.setdefault(part, {'files': {}})['files']
        node[parts[-1]] = {'offset': str(len(payload)), 'size': len(content)}
        payload.extend(content)
    header = json.dumps({'files': files}, separators=(',', ':')).encode()
    path.write_bytes(struct.pack('<4I', 4, 8 + len(header), 4 + len(header), len(header)) +
                     header + payload)
    return hashlib.sha256(path.read_bytes()).hexdigest()


class WindowsHostTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.app = self.base / 'original'
        self.archive = self.app / 'app/resources/app.asar'
        self.archive.parent.mkdir(parents=True)
        self.main = b'function Wre() { return 1; }'
        self.members = {windows_host.MAIN: self.main}
        self.members.update({name: name.encode() for name in windows_host.ORIGINAL_FILES})

    def _extract(self, expected):
        with patch.multiple(windows_host, MAIN_SHA256=hashlib.sha256(self.main).hexdigest(),
                            HOST_START=0, HOST_END=len(self.main),
                            HOST_SHA256=hashlib.sha256(self.main).hexdigest()):
            return windows_host.materialize_original_host(
                self.app, self.base / 'derived', expected_asar_sha256=expected)

    def test_extracts_original_bytes_and_entry_from_pinned_asar(self):
        expected = _asar(self.archive, self.members)
        entry = self._extract(expected)
        self.assertIn(self.main, entry.read_bytes())
        self.assertNotIn(windows_host.MARKER, entry.read_bytes())
        for name in windows_host.ORIGINAL_FILES:
            self.assertEqual((entry.parent / name).read_bytes(), self.members[name])

    def test_rejects_changed_asar_before_writing_host(self):
        expected = _asar(self.archive, self.members)
        self.archive.write_bytes(self.archive.read_bytes() + b'tampered')
        with self.assertRaisesRegex(ValueError, 'does not match'):
            self._extract(expected)
        self.assertFalse((self.base / 'derived').exists())

    def test_rejects_missing_source_member_before_writing_host(self):
        self.members.pop(windows_host.ORIGINAL_FILES[-1])
        expected = _asar(self.archive, self.members)
        with self.assertRaisesRegex(ValueError, 'member is missing'):
            self._extract(expected)
        self.assertFalse((self.base / 'derived').exists())

    def test_host_ready_handshake_and_owned_child_disposal(self):
        entry = self.base / 'host.py'
        entry.write_text("import json, sys\nprint(json.dumps({'ready': True, "
                         "'pipePath': r'\\\\.\\pipe\\lcu-wre-fixture'}), flush=True)\n"
                         "sys.stdin.buffer.read()\n")
        helper = self.base / 'helper.exe'
        transport = self.base / 'transport.js'
        helper.touch()
        transport.touch()
        process, pipe = windows_host.start_original_host(
            node=Path(sys.executable), entry=entry, helper=helper, transport=transport, env={})
        self.assertEqual(pipe, r'\\.\pipe\lcu-wre-fixture')
        windows_host.stop_original_host(process)
        self.assertEqual(process.returncode, 0)

    def test_host_early_exit_is_an_error(self):
        entry = self.base / 'host.py'
        entry.write_text("print('not ready', flush=True)\n")
        helper = self.base / 'helper.exe'
        transport = self.base / 'transport.js'
        helper.touch()
        transport.touch()
        with self.assertRaisesRegex(ValueError, 'failed to become ready'):
            windows_host.start_original_host(
                node=Path(sys.executable), entry=entry, helper=helper, transport=transport, env={})


if __name__ == '__main__':
    unittest.main()
