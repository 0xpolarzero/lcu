"""Windows subprocess stdout uses a reader thread because select() rejects pipes."""

import subprocess
import sys
import unittest
from unittest import mock

from lcu.app_server import AppServer


class WindowsPipeTests(unittest.TestCase):
    def test_real_subprocess_pipe_handles_two_rpc_replies_without_selector(self):
        script = ('import json,sys\n'
                  'for line in sys.stdin:\n'
                  ' req=json.loads(line)\n'
                  ' if "id" in req:\n'
                  '  sys.stdout.write(json.dumps({"id":req["id"],"result":{"method":req["method"]}})+"\\n")\n'
                  '  sys.stdout.flush()\n')
        process = subprocess.Popen([sys.executable, '-u', '-c', script],
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        try:
            with mock.patch('lcu.app_server._WINDOWS_PIPES', True), \
                 mock.patch('lcu.app_server.selectors.DefaultSelector',
                            side_effect=AssertionError('Windows pipe reached select')):
                client = AppServer(process)
                self.assertIsNone(client.selector)
                self.assertEqual(client.initialization, {'method': 'initialize'})
                self.assertEqual(client('ping', {}), {'method': 'ping'})
        finally:
            process.stdin.close()
            process.wait(timeout=5)
            process.stdout.close()


if __name__ == '__main__':
    unittest.main()
