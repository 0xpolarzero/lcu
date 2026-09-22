// Original queue/parser and real Electron window; no account or network access.
const assert = require('node:assert/strict');
const path = require('node:path');
const {app, BrowserWindow} = require('electron');
app.whenReady().then(async () => {
 let window, otherWindow;
 try {
  const createDeepLinks = require(process.env.LCU_DEEP_LINK_MODULE);
  const routes = [], httpUrls = [], failures = [];
  let available = false;
  window = new BrowserWindow({show:false});
  const queue = createDeepLinks(path.dirname(process.env.LCU_IAB_PROVIDER_PATH), {
   getPrimaryWindow: () => available ? window : null,
   ensurePrimaryWindowVisible: async () => available ? window : null,
   navigateToRoute: async (owner, route) => {
    assert.equal(owner, window);
    if (route.kind === 'launch') throw Error('fixture route-handler failure');
    routes.push(route);
   },
   openHttpUrl: async (owner, url) => {assert.equal(owner,window);httpUrls.push(url);},
   initialArgv: [],
   errorReporter: {reportNonFatal(error, details) {failures.push({message:error.message,kind:details.kind});}},
  });
  const callback = 'codex://connector/oauth_callback?code=fixture-code&state=fixture-state';
  assert.equal(queue.queueCodexDeepLinkUrl(callback), true);
  assert.equal(queue.queueCodexDeepLinkUrl('https://example.test/not-a-codex-route'), false);
  await new Promise(resolve => setImmediate(resolve));
  assert.deepEqual(routes, [], 'Original queue must wait for a real owner');
  available = true;
  await queue.flushPendingDeepLinks();
  assert.equal(routes.length, 1);
  assert.equal(routes[0].kind, 'connectorOAuthCallback');
  assert.equal(routes[0].fullRedirectUrl, callback);
  assert.equal(queue.queueCodexDeepLinkUrl('https://example.test/'), false);
  assert.equal(queue.queueProcessArgs(['lcu', 'https://example.test/fixture']), true);
  await new Promise(resolve => setImmediate(resolve));
  assert.deepEqual(httpUrls, ['https://example.test/fixture']);
  assert.equal(queue.queueCodexDeepLinkUrl('codex://launch'), true);
  await new Promise(resolve => setImmediate(resolve));
  assert.deepEqual(failures, [{message:'fixture route-handler failure',kind:'flush-pending-deep-links'}]);
  otherWindow = new BrowserWindow({show:false});
  const otherRoutes = [];
  const otherQueue = createDeepLinks(path.dirname(process.env.LCU_IAB_PROVIDER_PATH), {
   getPrimaryWindow: () => otherWindow,
   ensurePrimaryWindowVisible: async () => otherWindow,
   navigateToRoute: async (owner, route) => {
    assert.equal(owner, otherWindow);
    otherRoutes.push(route);
   },
   initialArgv: [],
   errorReporter: {reportNonFatal(error) {throw error;}},
  });
  const otherCallback = 'codex://connector/oauth_callback?code=other-fixture-code&state=other-fixture-state';
  assert.equal(otherQueue.queueCodexDeepLinkUrl(otherCallback), true);
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(otherRoutes.length, 1);
  assert.equal(otherRoutes[0].fullRedirectUrl, otherCallback);
  assert.equal(routes.length, 1, 'Original queue must not send another owner its callback');
  console.log(JSON.stringify({originalQueue:'PASS',originalRouteParser:'PASS',realWindowOwnership:'PASS',ownerIsolation:'PASS',invalidUrl:'PASS',linuxHttpArguments:'PASS',routeFailureReporting:'PASS',authenticatedOAuthCompletion:'NOT EXERCISED'}));
 } catch(error) {console.error(error.stack);process.exitCode=1;}
 finally {window?.destroy();otherWindow?.destroy();app.exit(process.exitCode || 0);}
});
