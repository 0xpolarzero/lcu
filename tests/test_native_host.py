"""The relay changes only the official extension's header capability reply."""
import io
import json
from pathlib import Path
import struct
import sys
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lcu.native_host import _enable_agent_header, _read_frame, _relay


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


if __name__ == '__main__':
    unittest.main()
