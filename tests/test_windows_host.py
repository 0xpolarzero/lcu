"""Pinned Windows host extraction from a disposable ASAR fixture."""

import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import struct
import subprocess
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
        self.assertTrue((entry.parent / 'windows-lifetime-host.cjs').is_file())
        self.assertTrue((entry.parent / 'windows-sky-service.mjs').is_file())

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
                         "'pipePath': r'\\\\.\\pipe\\lcu-wre-fixture', "
                         "'lifetimePath': r'\\\\.\\pipe\\lcu-lifetime-fixture'}), flush=True)\n"
                         "sys.stdin.buffer.read()\n")
        helper = self.base / 'helper.exe'
        transport = self.base / 'transport.js'
        helper.touch()
        transport.touch()
        process, pipe, lifetime = windows_host.start_original_host(
            node=Path(sys.executable), entry=entry, helper=helper, transport=transport, env={})
        self.assertEqual(pipe, r'\\.\pipe\lcu-wre-fixture')
        self.assertEqual(lifetime, r'\\.\pipe\lcu-lifetime-fixture')
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

    @unittest.skipUnless(shutil.which('node') and sys.platform != 'win32',
                         'Unix socket test needs Node on a non-Windows test host')
    def test_private_lifetime_transport_forwards_ids_and_survives_disconnect(self):
        address = self.base / 'lifetime.sock'
        module = Path(windows_host.__file__).with_name('windows_lifetime_host.cjs')
        script = ("const {startLifetimeSignal}=require(process.argv[1]); "
                  "let active='new'; "
                  "startLifetimeSignal(async ({sessionId,turnId})=>{ "
                  "if(turnId==='disconnect'){await new Promise(r=>setTimeout(r,50)); return false;} "
                  "const matched=sessionId==='session'&&turnId===active; "
                  "if(matched)active=null; return matched; }, process.argv[2]) "
                  ".then(signal=>{console.log('ready'); process.stdin.resume(); "
                  "process.stdin.once('end',()=>signal.dispose().then(()=>process.exit(0)));});")
        child = subprocess.Popen([shutil.which('node'), '-e', script, str(module), str(address)],
                                 stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                 env={'PATH': os.environ.get('PATH', '')})
        def cleanup():
            if child.poll() is None:
                child.terminate()
                child.wait(timeout=5)
            for pipe in (child.stdin, child.stdout, child.stderr):
                if pipe and not pipe.closed:
                    pipe.close()
        self.addCleanup(cleanup)
        ready = child.stdout.readline()
        if not ready:
            error = child.stderr.read()
            if b'listen EPERM' in error:
                self.skipTest('Local sandbox denies Unix socket listening')
            self.fail(f'Private lifetime host did not start: {error.decode(errors="replace")[:300]}')
        self.assertEqual(ready, b'ready\n')

        def call(turn):
            with socket.socket(socket.AF_UNIX) as client:
                client.connect(str(address))
                client.sendall(json.dumps({'session_id': 'session', 'turn_id': turn}).encode() + b'\n')
                with client.makefile('rb') as stream:
                    return json.loads(stream.readline())

        self.assertEqual(call('old'), {'closed': False})
        with socket.socket(socket.AF_UNIX) as dropped:
            dropped.connect(str(address))
            dropped.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack('ii', 1, 0))
            dropped.sendall(b'{"session_id":"session","turn_id":"disconnect"}\n')
        # A peer reset during the asynchronous host response must not crash it.
        import time
        time.sleep(0.1)
        self.assertIsNone(child.poll())
        self.assertEqual(call('new'), {'closed': True})
        self.assertEqual(call('new'), {'closed': False})
        child.stdin.close()
        self.assertEqual(child.wait(timeout=5), 0)
        child.stdout.close()

    @unittest.skipUnless(shutil.which('node'), 'Node is needed for trusted-service forwarding test')
    def test_sky_wrapper_registers_once_and_forwards_original_service(self):
        original = self.base / 'original-sky.mjs'
        original.write_text('export function handleRpc(request) { return request.type; }\n')
        wrapper = Path(windows_host.__file__).with_name('windows_sky_service.mjs')
        script = r'''import {pathToFileURL} from 'node:url';
let handlers = 0, ended = false, written, callback;
const listeners = {};
const socket = {
  on(name, fn) { listeners[name] = fn; return this; },
  write(bytes) {
    written = Buffer.from(bytes).toString('utf8');
    queueMicrotask(() => listeners.data(Buffer.from('{"closed":true}\n')));
  },
  end() { ended = true; },
};
globalThis.nodeRepl = {
  env: {LCU_WRE_SKY_SERVICE_PATH: process.argv[2], LCU_WRE_LIFETIME_PIPE: 'fixture'},
  nativePipe: {createConnection: async () => socket},
  addTurnEndedHandler(handler) { handlers++; callback = handler.run; },
};
const service = await import(pathToFileURL(process.argv[1]).href);
const first = await service.handleRpc({type:'setup'});
const second = await service.handleRpc({type:'execute'});
await callback({session_id:'session', turn_id:'turn'});
console.log(JSON.stringify({first, second, handlers, ended, written}));'''
        result = subprocess.run([shutil.which('node'), '--input-type=module', '-e', script,
                                 str(wrapper), str(original)], check=True, capture_output=True,
                                env={'PATH': os.environ.get('PATH', '')})
        self.assertEqual(json.loads(result.stdout),
                         {'first': 'setup', 'second': 'execute', 'handlers': 1,
                          'ended': True, 'written': '{"session_id":"session","turn_id":"turn"}\n'})


if __name__ == '__main__':
    unittest.main()
