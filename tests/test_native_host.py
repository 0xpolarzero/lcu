"""The relay changes only the official extension's header capability reply."""
import io
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest import mock


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lcu.native_host import _enable_agent_header, _original_host, _read_frame, _relay


class NativeHostRelayTests(unittest.TestCase):
    def test_fresh_extension_reply_enables_labeled_agent_requests(self):
        original = {'jsonrpc': '2.0', 'id': 7,
                    'result': {'type': 'extension', 'agentRequestHeaderEnabled': False,
                               'otherCapability': {'nested': True}}}
        result = json.loads(_enable_agent_header(json.dumps(original).encode()))
        self.assertEqual(result, {**original, 'result': {**original['result'],
                         'agentRequestHeaderEnabled': True}})

    def test_other_native_messages_remain_byte_identical(self):
        messages = [
            b'{ "result": {"type":"extension", "agentRequestHeaderEnabled":true} }',
            b'{ "result": {"type":"other", "agentRequestHeaderEnabled":false} }',
            b'{ "method":"event", "params":{"agentRequestHeaderEnabled":false} }',
            b'not json',
        ]
        for message in messages:
            with self.subTest(message=message):
                self.assertEqual(_enable_agent_header(message), message)

    def test_framed_stream_preserves_multiple_native_messages(self):
        messages = [b'{"id":1,"result":{"type":"extension","agentRequestHeaderEnabled":false}}',
                    b'{"id":2,"result":{"type":"other"}}']
        source = io.BytesIO(b''.join(struct.pack('<I', len(message)) + message for message in messages))
        destination = io.BytesIO()
        _relay(source, destination, _enable_agent_header)
        destination.seek(0)
        self.assertTrue(json.loads(_read_frame(destination))['result']['agentRequestHeaderEnabled'])
        self.assertEqual(_read_frame(destination), messages[1])
        self.assertIsNone(_read_frame(destination))

    def test_truncated_native_message_fails_closed(self):
        with self.assertRaisesRegex(ValueError, 'Short native-message body'):
            _read_frame(io.BytesIO(struct.pack('<I', 20) + b'partial'))

    def test_original_host_selects_installed_platform_binary(self):
        with tempfile.TemporaryDirectory() as temporary:
            relay = Path(temporary) / 'lcu-native-host'
            relay.write_text('fixture')
            for system, machine, segment, name in (
                ('Linux', 'x86_64', 'linux/x64', 'extension-host'),
                ('Linux', 'aarch64', 'linux/arm64', 'extension-host'),
                ('Darwin', 'arm64', 'macos/arm64', 'ChatGPT for Chrome'),
                ('Darwin', 'x86_64', 'macos/x64', 'ChatGPT for Chrome'),
            ):
                expected = relay.parent / 'chrome/extension-host' / segment / name
                expected.parent.mkdir(parents=True, exist_ok=True)
                expected.write_text('fixture')
                with self.subTest(system=system, machine=machine), \
                        mock.patch('lcu.native_host.__file__', str(relay)), \
                        mock.patch('lcu.native_host.platform.system', return_value=system), \
                        mock.patch('lcu.native_host.platform.machine', return_value=machine):
                    self.assertEqual(_original_host(), expected.resolve())

    def test_missing_original_host_fails_closed(self):
        with tempfile.TemporaryDirectory() as temporary, \
                mock.patch('lcu.native_host.__file__', str(Path(temporary) / 'relay')), \
                mock.patch('lcu.native_host.platform.system', return_value='Darwin'), \
                mock.patch('lcu.native_host.platform.machine', return_value='arm64'):
            with self.assertRaisesRegex(ValueError, 'original Chrome native host is missing'):
                _original_host()


if __name__ == '__main__':
    unittest.main()
