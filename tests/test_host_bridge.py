"""Independent process/pipe failure tests for the standalone host boundary."""
import os
from contextlib import redirect_stderr
from io import StringIO
from pathlib import Path
import subprocess
import selectors
import sys
import tempfile
import threading
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from lcu.app_server import app_server
from lcu.host_bridge import BrowserHost, session_id


class StubSubscription:
    def receive(self, _): return None
    def close(self): pass


class StubServer:
    notifications = []
    def receive(self, _): return None
    def subscribe_notifications(self): return StubSubscription()


class HostBoundaryTests(unittest.TestCase):
    def make_pipe_host(self, folder, child_script):
        host = BrowserHost(Path(folder), {}, 'owner')
        host.sessions.add('owner')
        host.process = subprocess.Popen([sys.executable, '-c', child_script],
                                        stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        host.selector = selectors.DefaultSelector()
        host.selector.register(host.process.stdout, selectors.EVENT_READ)
        host.server = StubServer()
        host.notification_subscription = host.server.subscribe_notifications()
        return host

    def test_unowned_deep_link_is_rejected_before_pipe_forwarding(self):
        script = "import select,sys; ready,_,_=select.select([sys.stdin],[],[],0.3); print('FORWARDED' if ready else 'NO_INPUT',flush=True)"
        with tempfile.TemporaryDirectory() as folder:
            host = self.make_pipe_host(folder, script)
            with self.assertRaisesRegex(ValueError, 'existing owned session'):
                host.deliver_deep_link('stranger', 'sample://oauth/callback?code=fixture')
            self.assertEqual(host.process.stdout.readline().strip(), b'NO_INPUT')
            host.process.wait(timeout=2)
            host.selector.close()
            host.process.stdout.close()
            host.process.stdin.close()

    def test_deep_link_wait_ignores_ack_for_another_request_id(self):
        script = r'''
import json,sys,time
event=json.loads(sys.stdin.readline())
assert event['type']=='deep-link'
print(json.dumps({'lcuHost':'deep-link','requestId':'stale','sessionId':event['sessionId'],'accepted':True}),flush=True)
time.sleep(0.05)
print(json.dumps({'lcuHost':'deep-link','requestId':event['requestId'],'sessionId':event['sessionId'],'accepted':True}),flush=True)
'''
        with tempfile.TemporaryDirectory() as folder:
            host = self.make_pipe_host(folder, script)
            try:
                result = host.deliver_deep_link('owner', 'sample://oauth/callback?code=fixture')
                self.assertEqual(result['sessionId'], 'owner')
                self.assertTrue(result['accepted'])
                self.assertNotEqual(result['requestId'], 'stale')
                self.assertTrue(any(event.get('requestId') == 'stale' for event in host.events))
            finally:
                host.process.wait(timeout=2)
                host.selector.close()
                host.process.stdout.close()
                host.process.stdin.close()

    def test_deep_link_acceptance_only_reports_queue_acknowledgement(self):
        script = r'''
import json,sys
event=json.loads(sys.stdin.readline())
print(json.dumps({'lcuHost':'deep-link','requestId':event['requestId'],'sessionId':event['sessionId'],'accepted':True}),flush=True)
'''
        with tempfile.TemporaryDirectory() as folder:
            host = self.make_pipe_host(folder, script)
            try:
                result = host.deliver_deep_link('owner', 'sample://oauth/callback?code=fixture')
                self.assertEqual(result, {'lcuHost':'deep-link', 'requestId':result['requestId'],
                                          'sessionId':'owner', 'accepted':True})
                self.assertNotIn('authenticated', result)
                self.assertNotIn('loginSucceeded', result)
            finally:
                host.process.wait(timeout=2)
                host.selector.close()
                host.process.stdout.close()
                host.process.stdin.close()

    def test_shutdown_delivers_pending_original_settings_write_before_exit(self):
        script = r'''
import json,sys
assert json.loads(sys.stdin.readline())['type']=='shutdown'
print(json.dumps({'lcuHost':'app-server-request','requestId':'flush','method':'config/batchWrite','params':{'edits':[{'keyPath':'desktop.browser-download-directory','mergeStrategy':'replace','value':'/fixture'}]}}),flush=True)
reply=json.loads(sys.stdin.readline())
assert reply['requestId']=='flush' and reply['result']=={'status':'ok'},reply
open(sys.argv[1],'w').write('flushed before normal exit')
'''
        class Connection:
            notifications = []
            def receive(self, _): return None
            def subscribe_notifications(self): return StubSubscription()
            def __call__(self, method, params):
                self.assertion = (method, params)
                return {'status': 'ok'}
        with tempfile.TemporaryDirectory() as folder:
            outcome = Path(folder) / 'outcome'
            host = BrowserHost(Path(folder), {}, 'fixture')
            host.server = Connection()
            host.notification_subscription = host.server.subscribe_notifications()
            host.process = subprocess.Popen([sys.executable, '-c', script, str(outcome)],
                                            stdin=subprocess.PIPE, stdout=subprocess.PIPE)
            host.selector = selectors.DefaultSelector()
            host.selector.register(host.process.stdout, selectors.EVENT_READ)
            host.stack.callback(host.selector.close)
            host.close()
            self.assertEqual(host.process.returncode, 0)
            self.assertEqual(outcome.read_text(), 'flushed before normal exit')
            self.assertEqual(host.server.assertion[0], 'config/batchWrite')

    def test_original_nonfatal_report_does_not_abort_graceful_shutdown(self):
        script = r'''
import json,sys,time
assert json.loads(sys.stdin.readline())['type']=='shutdown'
print(json.dumps({'lcuHost':'nonfatal','kind':'browser-sidebar-comment-screenshot','message':'UnknownVizError'}),flush=True)
time.sleep(0.1)
'''
        with tempfile.TemporaryDirectory() as folder:
            host = self.make_pipe_host(folder, script)
            output = StringIO()
            with redirect_stderr(output):
                host.close()
            self.assertEqual(host.process.returncode, 0)
            self.assertIn('UnknownVizError', output.getvalue())

    def test_fatal_host_error_still_aborts_graceful_shutdown(self):
        script = r'''
import json,sys,time
assert json.loads(sys.stdin.readline())['type']=='shutdown'
print(json.dumps({'lcuHost':'error','message':'fatal fixture failure'}),flush=True)
time.sleep(0.1)
'''
        with tempfile.TemporaryDirectory() as folder:
            host = self.make_pipe_host(folder, script)
            with self.assertRaisesRegex(ValueError, 'did not complete graceful shutdown') as failure:
                host.close()
            self.assertIn('fatal fixture failure', str(failure.exception.__cause__))

    def test_host_notification_poll_cannot_consume_concurrent_parent_rpc_reply(self):
        with tempfile.TemporaryDirectory() as folder:
            ready = Path(folder) / 'request-ready'
            release = Path(folder) / 'release-response'
            app_script = r'''
import json,sys,time
from pathlib import Path
ready,release=map(Path,sys.argv[1:])
def send(value):print(json.dumps(value),flush=True)
for line in sys.stdin:
    message=json.loads(line)
    if message.get('method')=='initialize':
        send({'id':message['id'],'result':{'userAgent':'Codex/1.2.3'}})
    elif message.get('method')=='fixture/read':
        ready.write_text('sent')
        while not release.exists():time.sleep(.002)
        send({'id':'server-request-1','method':'fixture/callback','params':{'token':'opaque'}})
        callback=json.loads(sys.stdin.readline())
        assert callback=={'id':'server-request-1','result':{'handled':'by-caller'}},callback
        send({'id':message['id'],'result':{'value':'rpc-response'}})
        send({'method':'fixture/updated','params':{'fixture':True}})
'''
            ui_script = r'''
import json,sys
for line in sys.stdin:
    event=json.loads(line)
    if event.get('type')=='shutdown':break
    print(json.dumps({'lcuHost':'observed','event':event}),flush=True)
'''
            app_process = subprocess.Popen([sys.executable, '-c', app_script, str(ready), str(release)],
                                           stdin=subprocess.PIPE, stdout=subprocess.PIPE)
            from lcu.app_server import AppServer
            handled_requests = []
            def handle_server_request(request):
                handled_requests.append(request)
                return {'id':request['id'],'result':{'handled':'by-caller'}}
            server = AppServer(app_process, request_handler=handle_server_request)
            host = BrowserHost(Path(folder), {}, 'fixture', app_server_connection=server)
            host.server = server
            host.notification_subscription = server.subscribe_notifications()
            second_subscription = server.subscribe_notifications()
            buffered_subscription = server.subscribe_notifications()
            host.process = subprocess.Popen([sys.executable, '-c', ui_script],
                                            stdin=subprocess.PIPE, stdout=subprocess.PIPE)
            host.selector = selectors.DefaultSelector()
            host.selector.register(host.process.stdout, selectors.EVENT_READ)

            request_written = threading.Event()
            allow_caller_to_read = threading.Event()
            original_send = server.send
            def gated_send(message):
                original_send(message)
                if message.get('method') == 'fixture/read':
                    request_written.set()
                    if not allow_caller_to_read.wait(5):
                        raise TimeoutError('test did not release RPC reader')
            server.send = gated_send
            result, failure = [], []
            def call_rpc():
                try:
                    result.append(server('fixture/read', {}, timeout=3))
                except BaseException as error:
                    failure.append(error)
            caller = threading.Thread(target=call_rpc)
            try:
                caller.start()
                self.assertTrue(request_written.wait(2), 'parent RPC request was not written')
                deadline = time.monotonic() + 2
                while not ready.exists() and time.monotonic() < deadline:
                    time.sleep(.002)
                self.assertTrue(ready.exists(), 'app-server did not receive the RPC')
                release.write_text('go')
                # The reply precedes the event. Polling must route the reply to
                # its caller and keep reading until this subscriber gets the event.
                deadline = time.monotonic() + 2
                while not any(event.get('lcuHost') == 'observed' for event in host.events) and time.monotonic() < deadline:
                    host.poll(.01)
                self.assertTrue(any(event.get('lcuHost') == 'observed' for event in host.events),
                                'notification did not reach the host pipe')
                allow_caller_to_read.set()
                caller.join(timeout=2)
                self.assertFalse(caller.is_alive(), 'parent RPC caller remained blocked')
                self.assertEqual(failure, [])
                self.assertEqual(result, [{'value': 'rpc-response'}])
                self.assertEqual(handled_requests, [{'id':'server-request-1','method':'fixture/callback',
                                                     'params':{'token':'opaque'}}])
                observed = next(event['event'] for event in host.events if event.get('lcuHost') == 'observed')
                self.assertEqual(observed['type'], 'notification')
                self.assertEqual(observed['notification']['method'], 'fixture/updated')
                self.assertEqual(second_subscription.receive(0), observed['notification'])
                self.assertEqual(buffered_subscription.messages, [observed['notification']])
                buffered_subscription.close()
                self.assertEqual(buffered_subscription.messages, [])
            finally:
                allow_caller_to_read.set()
                if caller.is_alive():
                    caller.join(timeout=2)
                second_subscription.close()
                buffered_subscription.close()
                host.close()
                if app_process.poll() is None:
                    app_process.terminate()
                app_process.wait(timeout=2)
                app_process.stdout.close()
                app_process.stdin.close()

    def test_parent_request_without_handler_gets_explicit_unsupported_error(self):
        app_script = r'''
import json,sys
def send(value):print(json.dumps(value),flush=True)
for line in sys.stdin:
    message=json.loads(line)
    if message.get('method')=='initialize':
        send({'id':message['id'],'result':{'userAgent':'Codex/1.2.3'}})
    elif message.get('method')=='fixture/read':
        send({'id':'unsupported-request','method':'fixture/callback','params':{}})
        response=json.loads(sys.stdin.readline())
        assert response=={'id':'unsupported-request','error':{
            'code':-32601,'message':'Server-originated requests are unsupported.'}},response
        send({'id':message['id'],'result':{'value':'still-correlated'}})
'''
        app_process = subprocess.Popen([sys.executable, '-c', app_script],
                                       stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        from lcu.app_server import AppServer
        server = AppServer(app_process)
        try:
            self.assertEqual(server('fixture/read', {}, timeout=2), {'value':'still-correlated'})
        finally:
            if app_process.poll() is None:
                app_process.terminate()
            app_process.wait(timeout=2)
            app_process.stdout.close()
            app_process.stdin.close()

    def test_parent_request_handler_error_is_returned_with_original_id(self):
        app_script = r'''
import json,sys
def send(value):print(json.dumps(value),flush=True)
for line in sys.stdin:
    message=json.loads(line)
    if message.get('method')=='initialize':
        send({'id':message['id'],'result':{'userAgent':'Codex/1.2.3'}})
    elif message.get('method')=='fixture/read':
        send({'id':'error-request','method':'fixture/reject','params':{'reason':'caller policy'}})
        response=json.loads(sys.stdin.readline())
        assert response=={'id':'error-request','error':{
            'code':-32042,'message':'caller rejected','data':{'reason':'policy'} }},response
        send({'id':message['id'],'result':{'value':'outer-response'}})
'''
        def reject(request):
            self.assertEqual(request['method'], 'fixture/reject')
            return {'id':request['id'],'error':{'code':-32042,'message':'caller rejected',
                                                'data':{'reason':'policy'}}}
        app_process = subprocess.Popen([sys.executable, '-c', app_script],
                                       stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        from lcu.app_server import AppServer
        server = AppServer(app_process, request_handler=reject)
        try:
            self.assertEqual(server('fixture/read', {}, timeout=2), {'value':'outer-response'})
        finally:
            if app_process.poll() is None:
                app_process.terminate()
            app_process.wait(timeout=2)
            app_process.stdout.close()
            app_process.stdin.close()

    def test_invalid_request_handler_envelope_emits_no_reply_and_clears_pending(self):
        app_script = r'''
import json,select,sys
from pathlib import Path
outcome=Path(sys.argv[1])
def send(value):print(json.dumps(value),flush=True)
for line in sys.stdin:
    message=json.loads(line)
    if message.get('method')=='initialize':
        send({'id':message['id'],'result':{'userAgent':'Codex/1.2.3'}})
    elif message.get('method')=='fixture/read':
        send({'id':'invalid-request','method':'fixture/callback','params':{}})
        ready,_,_=select.select([sys.stdin],[],[],0.2)
        outcome.write_text(sys.stdin.readline() if ready else 'no reply')
        break
'''
        with tempfile.NamedTemporaryFile() as temporary:
            outcome_path = temporary.name
        app_process = subprocess.Popen([sys.executable, '-c', app_script, outcome_path],
                                       stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        from lcu.app_server import AppServer
        server = AppServer(app_process, request_handler=lambda request: {
            'id':request['id'], 'method':'not-a-response', 'result':{'accepted':True}})
        outcome = Path(outcome_path)
        try:
            with self.assertRaisesRegex(ValueError, 'invalid response envelope'):
                server('fixture/read', {}, timeout=2)
            app_process.wait(timeout=2)
            self.assertEqual(outcome.read_text(), 'no reply')
            self.assertEqual(server._pending, set())
            self.assertEqual(server._responses, {})
        finally:
            if app_process.poll() is None:
                app_process.terminate()
            app_process.wait(timeout=2)
            app_process.stdout.close()
            app_process.stdin.close()
            outcome.unlink(missing_ok=True)

    def test_parent_request_handler_can_make_nested_rpc(self):
        app_script = r'''
import json,sys
def send(value):print(json.dumps(value),flush=True)
outer_id=None
for line in sys.stdin:
    message=json.loads(line)
    if message.get('method')=='initialize':
        send({'id':message['id'],'result':{'userAgent':'Codex/1.2.3'}})
    elif message.get('method')=='fixture/read':
        outer_id=message['id']
        send({'id':'nested-request','method':'fixture/callback','params':{}})
    elif message.get('method')=='fixture/nested':
        send({'id':message['id'],'result':{'nested':'complete'}})
    elif message.get('id')=='nested-request':
        assert message=={'id':'nested-request','result':{'nested':'complete'}},message
        send({'id':outer_id,'result':{'outer':'complete'}})
'''
        app_process = subprocess.Popen([sys.executable, '-c', app_script],
                                       stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        from lcu.app_server import AppServer
        server = AppServer(app_process)
        def handle(request):
            nested = server('fixture/nested', {}, timeout=2)
            return {'id':request['id'], 'result':nested}
        server.request_handler = handle
        try:
            self.assertEqual(server('fixture/read', {}, timeout=2), {'outer':'complete'})
            self.assertEqual(server._pending, set())
        finally:
            if app_process.poll() is None:
                app_process.terminate()
            app_process.wait(timeout=2)
            app_process.stdout.close()
            app_process.stdin.close()

    def test_unsolicited_jsonrpc_response_does_not_answer_another_call(self):
        app_script = r'''
import json,sys,time
def send(value):print(json.dumps(value),flush=True)
for line in sys.stdin:
    message=json.loads(line)
    if message.get('method')=='initialize':
        send({'id':message['id'],'result':{'userAgent':'Codex/1.2.3'}})
    elif message.get('method')=='fixture/read':
        send({'id':message['id']+99,'result':{'accepted':True}})
        send({'id':message['id'],'result':{'value':'actual'}})
'''
        app_process = subprocess.Popen([sys.executable, '-c', app_script],
                                       stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        from lcu.app_server import AppServer
        server = AppServer(app_process)
        try:
            self.assertEqual(server('fixture/read', {}, timeout=2), {'value':'actual'})
            self.assertEqual(server._responses, {})
        finally:
            if app_process.poll() is None:
                app_process.terminate()
            app_process.wait(timeout=2)
            app_process.stdout.close()
            app_process.stdin.close()

    def test_native_subagent_metadata_routes_cleanup_to_child_thread(self):
        # Shape observed from original Codex spawn_agent and SubagentStop; the
        # root session ID must not be used to claim the child's browser route.
        turn = {'session_id': 'root', 'thread_id': 'child', 'thread_source': 'subagent',
                'subagent_kind': 'thread_spawn', 'parent_thread_id': 'root', 'turn_id': 'child-turn'}
        self.assertEqual(session_id({'x-codex-turn-metadata': turn}), 'child')
        turn['thread_source'] = 'cli'
        self.assertEqual(session_id({'x-codex-turn-metadata': turn}), 'root')

    def test_initialization_eof_does_not_leak_file_descriptors(self):
        if not Path('/dev/fd').exists():
            self.skipTest('Requires POSIX descriptor inventory')
        with tempfile.TemporaryDirectory() as folder:
            cli = Path(folder) / 'exiting-cli'
            cli.write_text('#!/bin/sh\nexit 23\n')
            cli.chmod(0o700)
            before = len(os.listdir('/dev/fd'))
            for _ in range(4):
                with self.assertRaisesRegex(ValueError, 'exited unexpectedly'):
                    with app_server(cli, folder, os.environ):
                        self.fail('Initialization unexpectedly succeeded')
            self.assertEqual(len(os.listdir('/dev/fd')), before)

    def test_policy_monitor_remains_live_when_mcp_stops_reading(self):
        # A real child process never reads stdin. A message larger than the OS
        # pipe fills it. The policy monitor must still run and close that child.
        script = r'''
import json,sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import lcu.host_bridge as bridge
class Host:
    def __init__(self,*_):self.active=False;self.polls=0
    def __enter__(self):return self
    def __exit__(self,*_):pass
    def register(self,_):self.active=True
    def poll(self,*_):
        if self.active:
            self.polls+=1
            if self.polls==6:raise RuntimeError('policy-invalidated-during-backpressure')
bridge.BrowserHost=Host
try:
    bridge.run_mcp(Path('/unused'), {'NODE_REPL_REQUEST_META':json.dumps({'x-codex-turn-metadata':{'session_id':'fixture'}})},
                   [sys.executable,'-c','import time;time.sleep(30)'])
except RuntimeError as error:
    print(error)
else:raise AssertionError('Policy monitor never invalidated the host')
'''
        message = b'{"method":"tools/call","params":{"padding":"' + b'x' * (2 * 1024 * 1024) + b'"}}\n'
        result = subprocess.run([sys.executable, '-c', script, str(ROOT)], input=message,
                                capture_output=True, timeout=8)
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        self.assertIn(b'policy-invalidated-during-backpressure', result.stdout)


if __name__ == '__main__':
    unittest.main()
