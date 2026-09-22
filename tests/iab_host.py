#!/usr/bin/env python3
"""Offline provider-level integration; this does not bypass client authentication."""
import base64
import json
import hashlib
from pathlib import Path
import socket
import select
import struct
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, str(Path(sys.argv[1]).resolve()))
from lcu.host_bridge import BrowserHost
from lcu.runtime import environment

class Fixture(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        if self.path == '/download':
            self.send_header('Content-Disposition', 'attachment; filename=fixture.txt')
            body=b'original IAB download\n'
        else:
            self.send_header('Content-Type', 'text/html')
            body=b'<!doctype html><title>LCU IAB fixture</title><button onclick="this.textContent=\'clicked\'">Fixture</button>'
        self.end_headers(); self.wfile.write(body)
    def log_message(self, *_): pass

class Pipe:
    def __init__(self, path, host):
        self.host=host
        self.socket=socket.socket(socket.AF_UNIX);self.socket.settimeout(25);self.socket.connect(str(path));self.counter=0
    def read(self,n):
        data=b''
        deadline=time.monotonic()+25
        while len(data)<n:
            self.host.poll()
            if not select.select([self.socket],[],[],.02)[0]:
                if time.monotonic()>deadline:raise TimeoutError('Original provider response timed out')
                continue
            chunk=self.socket.recv(n-len(data))
            if not chunk: raise AssertionError('Original provider closed its native pipe')
            data+=chunk
        return data
    def call(self, method, params):
        print('IAB STEP', method, params.get('method', ''), file=sys.stderr, flush=True)
        self.counter+=1
        data=json.dumps(dict(jsonrpc='2.0',id=self.counter,method=method,params=params)).encode()
        self.socket.sendall(struct.pack('<I',len(data))+data)
        while True:
            message=json.loads(self.read(struct.unpack('<I',self.read(4))[0]))
            if message.get('id')!=self.counter: continue
            if 'error' in message: raise RuntimeError(message['error']['message'])
            return message.get('result')

def main():
    root=Path(sys.argv[1]);env=environment(root)
    server=ThreadingHTTPServer(('127.0.0.1',0),Fixture)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    try:
        with BrowserHost(root,env,'iab-fixture',electron_args=['--no-sandbox']) as host:
            host.send({'type':'session','sessionId':'iab-fixture'})
            registration=host.wait('session','iab-fixture')
            expected_profile=Path(env.get('XDG_DATA_HOME',str(Path(env['HOME'])/'.local/share')))/'lcu/browser-profiles'/hashlib.sha256(b'iab-fixture').hexdigest()
            assert Path(registration['profilePath'])==expected_profile,registration
            # No account or OAuth redirect is invented. The mounted original
            # pending hook must reject missing state through the real owner IPC.
            oauth_rejected=host.register_app_connect_oauth('iab-fixture',{
                'app':{'id':'fixture-app','name':'Fixture'},'redirectUrl':'','returnTo':'/'})
            assert oauth_rejected['processed'] is True and oauth_rejected['registered'] is False,oauth_rejected
            oauth_no_state=host.register_app_connect_oauth('iab-fixture',{
                'app':{'id':'fixture-app','name':'Fixture'},
                'redirectUrl':'https://fixture.invalid/oauth/callback?code=synthetic','returnTo':'/'})
            assert oauth_no_state['processed'] is True and oauth_no_state['registered'] is False,oauth_no_state
            oauth_clear=host.clear_app_connect_oauth('iab-fixture',{'oauthState':'absent-fixture'})
            assert oauth_clear['processed'] is True,oauth_clear
            paths=list(Path('/tmp/codex-browser-use').glob('*.sock'))
            assert len(paths)==1, paths
            client=Pipe(paths[0],host);meta={'session_id':'iab-fixture','turn_id':'turn-1'}
            info=client.call('getInfo',meta);assert info['type']=='iab'
            host.send({'type':'features','policy':{'desktop':{'inAppBrowserUseHistory':True,'webMcp':True,'webMcpMaxTools':7}}})
            policy=host.wait('features',None)['policy']
            assert policy['desktop']['webMcpMaxTools']==7,policy
            assert client.call('getInfo',meta)['apiSupportOverrides']['Browser.history'] is True
            host.send({'type':'features','policy':{'desktop':{'inAppBrowserUseHistory':False,'webMcp':False,'webMcpMaxTools':100}}})
            host.wait('features',None)
            try: client.call('getInfo',dict(session_id='unowned-fixture'))
            except RuntimeError as error: assert 'route' in str(error).lower()
            else: raise AssertionError('Original registry accepted an unowned session')
            tab=client.call('createTab',meta);target={'tabId':tab['id']}
            def cdp(method,params=None): return client.call('executeCdp',{**meta,'target':target,'method':method,'commandParams':params or {}})
            cdp('Runtime.evaluate',{'expression':'document.title','returnByValue':True})
            cdp('Runtime.enable')
            cdp('Page.enable')
            url=f'http://127.0.0.1:{server.server_port}/'
            navigation=cdp('Page.navigate',{'url':url})
            assert not navigation.get('errorText'),navigation
            deadline=time.monotonic()+5
            while time.monotonic()<deadline:
                tabs=client.call('getTabs',meta)
                if tabs[0]['title']=='LCU IAB fixture':break
                time.sleep(.1)
            assert tabs[0]['title']=='LCU IAB fixture',tabs
            result=cdp('Runtime.evaluate',{'expression':'document.title','returnByValue':True})
            assert result['result']['value']=='LCU IAB fixture',result
            # Actual auxiliary mouse navigation originates in the unchanged page
            # preload and invokes the original global runtime-message dispatcher.
            cdp('Page.navigate',{'url':url+'next'})
            deadline=time.monotonic()+5
            while time.monotonic()<deadline:
                readiness=cdp('Runtime.evaluate',{'expression':'document.readyState+location.pathname','returnByValue':True})['result'].get('value')
                if readiness=='complete/next':break
                time.sleep(.05)
            assert readiness=='complete/next',readiness
            cdp('Runtime.evaluate',{'expression':"window.__lcuMouse=[];window.addEventListener('mouseup',e=>window.__lcuMouse.push({button:e.button,trusted:e.isTrusted}),true)"})
            for kind in ('mousePressed','mouseReleased'):
                cdp('Input.dispatchMouseEvent',{'type':kind,'button':'back','x':50,'y':50,'clickCount':1})
            deadline=time.monotonic()+5
            while time.monotonic()<deadline:
                pathname=cdp('Runtime.evaluate',{'expression':'location.pathname','returnByValue':True})['result'].get('value')
                if pathname=='/':break
                time.sleep(.05)
            assert pathname=='/',(pathname,cdp('Runtime.evaluate',{'expression':'window.__lcuMouse','returnByValue':True}))
            image=base64.b64decode(cdp('Page.captureScreenshot',{'format':'png'})['data'])
            assert image.startswith(b'\x89PNG\r\n\x1a\n')
            try: cdp('Page.navigate',{'url':'file:///etc/passwd'})
            except RuntimeError as error: assert 'URL policy' in str(error),error
            else: raise AssertionError('Original URL policy allowed a file URL')
            client.call('executeUnhandledCommand',{**meta,'type':'browser_visibility_set','browser_id':'iab','visible':True})
            visible=client.call('executeUnhandledCommand',{**meta,'type':'browser_visibility_get','browser_id':'iab'})
            assert visible['visible'],visible
            client.call('executeUnhandledCommand',{**meta,'type':'browser_viewport_set','browser_id':'iab','width':900,'height':650})
            dimensions=cdp('Runtime.evaluate',{'expression':'[innerWidth,innerHeight]','returnByValue':True})
            assert dimensions['result']['value']==[900,650],dimensions
            client.call('moveMouse',{**meta,'tabId':tab['id'],'x':30,'y':20,'waitForArrival':True})
            client.call('turnEnded',meta)
            assert client.call('getTabs',meta)==[]
            host.register('second-fixture')
            client.socket.close()
            print(json.dumps({'provider':'original full zZe/uX/fYe','real_cli_requirements':'PASS','actual_private_profile':'PASS','original_oauth_missing_state_rejection':'PASS','original_oauth_valid_url_no_state_rejection':'PASS','original_oauth_clear_invocation':'PASS','original_feature_hydration':'PASS','owned_route':'PASS','foreign_route_denied':'PASS','webview_navigation':'PASS','original_preload_mouse_navigation':'PASS','screenshot_png_bytes':len(image),'file_navigation_denied':'PASS','cursor':'PASS','turn_cleanup':'PASS','additional_actual_session':'PASS','authentication':'Not exercised: provider tests do not prove authenticated browser-client actions'},indent=2))
    finally: server.shutdown()

if __name__=='__main__': main()
