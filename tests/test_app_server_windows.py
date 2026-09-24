"""Windows subprocess stdout uses a reader thread because select() rejects pipes."""

import subprocess
import sys
import time
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

    def test_timeout_then_eof_remain_distinct(self):
        script = ('import json,sys,time\n'
                  'for line in sys.stdin:\n'
                  ' req=json.loads(line)\n'
                  ' if req.get("method") == "initialize":\n'
                  '  sys.stdout.write(json.dumps({"id":req["id"],"result":{}})+"\\n")\n'
                  '  sys.stdout.flush()\n'
                  ' elif req.get("method") == "ping":\n'
                  '  time.sleep(.2)\n'
                  '  break\n')
        process = subprocess.Popen([sys.executable, '-u', '-c', script],
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        try:
            with mock.patch('lcu.app_server._WINDOWS_PIPES', True):
                client = AppServer(process)
                with self.assertRaisesRegex(ValueError, 'timed out: ping'):
                    client('ping', {}, timeout=.02)
                process.wait(timeout=5)
                for _ in range(2):
                    with self.assertRaisesRegex(ValueError, 'exited unexpectedly'):
                        client.receive(timeout=.1)
        finally:
            process.stdin.close()
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=5)
            process.stdout.close()


if __name__ == '__main__':
    unittest.main()
