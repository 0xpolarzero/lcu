// The original wEe/Sf pair runs in Electron. Only network bytes are fixtures.
const assert = require('node:assert/strict');
const path = require('node:path');
const {EventEmitter} = require('node:events');
const {pathToFileURL} = require('node:url');
const {app, BrowserWindow, ipcMain} = require('electron');

app.whenReady().then(async () => {
 try {
  const generated = path.dirname(process.env.LCU_IAB_PROVIDER_PATH);
  const originalShared = require(path.join(process.env.LCU_APPLICATION_PATH,
   'resources/app.asar/.vite/build/src-C3YaUE83.js'));
  let calls = 0;
  const network = {
   assertAllowed(url) { if (!url.startsWith('https://fixture.example/')) throw Error('Fixture network denied URL'); },
   async fetch(url, init) {
    calls++;
   if (url.endsWith('/pending')) return new Promise((_resolve, reject) => {
     init.signal.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')),
      {once: true});
    });
    if (url.endsWith('/stream')) return new Response(new ReadableStream({
     start(controller) {
      controller.enqueue(new TextEncoder().encode('first chunk'));
      init.signal.addEventListener('abort',
       () => controller.error(new DOMException('Aborted', 'AbortError')), {once: true});
     },
    }), {status: 200, headers: {'content-type': 'text/plain'}});
    return new Response(JSON.stringify({ok: true}), {status: 200,
     headers: {'content-type': 'application/json'}});
   },
  };
  const service = require(path.join(process.env.LCU_TEST_RELEASE,
   'lcu/host/http-service.cjs'))(generated, {
   applicationNetwork: network,
   authClient: {getCachedAuthToken() {throw Error('Fixture must not read credentials');}},
   globalState: {get() {return undefined;}, update() {throw Error('Unexpected integrity update');}},
   originalShared,
   buildFlavor: 'prod',
  });
  class Owner extends EventEmitter {
   constructor(id) {super(); this.id = id; this.destroyed = false;}
   isDestroyed() {return this.destroyed;}
   send() {}
   destroy() {this.destroyed = true; this.emit('destroyed');}
  }
  const owner = new Owner(1);
  const ok = await service.fetch(owner, 'ok', {url: 'https://fixture.example/ok',
   method: 'GET', headers: {}});
  assert.ok(ok.response, JSON.stringify(ok));
  assert.equal(ok.response.status, 200);
  assert.equal(ok.response.bodyStream, true);
  const okChunk = await service.pull(owner, 'ok');
  assert.equal(okChunk.done, false);
  assert.deepEqual(JSON.parse(Buffer.from(okChunk.chunk).toString()), {ok: true});
  assert.equal((await service.pull(owner, 'ok')).done, true);
  assert.equal(calls, 1);
  const denied = await service.fetch(owner, 'denied', {url: 'https://elsewhere.example/',
   method: 'GET', headers: {}});
  assert.equal(denied.responseType, 'error');
  assert.match(denied.error, /Fixture network denied URL/);
  assert.equal(calls, 1);
  const recovered = await service.fetch(owner, 'recovered', {url: 'https://fixture.example/recovered',
   method: 'GET', headers: {}});
  assert.equal(recovered.response.status, 200);
  assert.equal((await service.pull(owner, 'recovered')).done, false);
  assert.equal((await service.pull(owner, 'recovered')).done, true);
  assert.equal(calls, 2, 'A denied request must not poison the original window provider');
  const pending = service.fetch(owner, 'pending', {url: 'https://fixture.example/pending',
   method: 'GET', headers: {}});
  await new Promise(resolve => setTimeout(resolve, 50));
  service.cancel(owner, 'pending');
  const aborted = await pending;
  assert.equal(aborted.responseType, 'error');
  assert.equal(aborted.status, 499);
  const stream = await service.fetch(owner, 'stream', {url: 'https://fixture.example/stream',
   method: 'GET', headers: {}});
  assert.equal(stream.response.bodyStream, true);
  const firstChunk = await Promise.race([
   service.pull(owner, 'stream'),
   new Promise((_resolve, reject) => setTimeout(() => reject(Error('First body chunk did not arrive before EOF')), 1000)),
  ]);
  assert.equal(firstChunk.done, false);
  assert.equal(Buffer.from(firstChunk.chunk).toString(), 'first chunk');
  service.cancel(owner, 'stream');
  await assert.rejects(service.pull(owner, 'stream'), /unavailable/);
  const {createHttpFetch} = await import(pathToFileURL(path.join(
   process.env.LCU_TEST_RELEASE, 'lcu/host/oauth-renderer.js')).href);
  const rendererHttp = createHttpFetch({
   subscribe() {},
   httpFetch: ({requestId, request, trackUploadProgress}) =>
    service.fetch(owner, requestId, request, trackUploadProgress),
   httpPull: requestId => service.pull(owner, requestId),
   httpCancel: requestId => Promise.resolve(service.cancel(owner, requestId)),
   httpDispose: requestId => Promise.resolve(service.dispose(owner, requestId)),
  });
  const rendererTask = rendererHttp.fetch('renderer-stream', {url: 'https://fixture.example/stream',
   method: 'GET', headers: {}});
  const rendererResult = await rendererTask;
  const rendererReader = rendererResult.response.body.getReader();
  const firstInRenderer = await Promise.race([
   rendererReader.read(),
   new Promise((_resolve, reject) => setTimeout(() => reject(Error('Renderer adapter did not receive first chunk before EOF')), 1000)),
  ]);
  assert.equal(firstInRenderer.done, false);
  assert.equal(new TextDecoder().decode(firstInRenderer.value), 'first chunk');
  await rendererReader.cancel();
  rendererResult[Symbol.dispose]();
  rendererTask[Symbol.dispose]();
  await assert.rejects(service.pull(owner, 'renderer-stream'), /unavailable/);
  const fixtureRoot = process.env.LCU_TEST_SOURCE;
  const rendererWindow = new BrowserWindow({show: false, webPreferences: {
   preload: path.join(fixtureRoot, 'tests/iab_http_preload.cjs'),
   contextIsolation: true, nodeIntegration: false, sandbox: true,
  }});
  const sender = rendererWindow.webContents;
  ipcMain.handle('fixture:http-fetch', (event, message) => {
   assert.equal(event.sender, sender);
   return service.fetch(sender, message.requestId, message.request,
    message.trackUploadProgress === true);
  });
  ipcMain.handle('fixture:http-pull', (event, id) => {
   assert.equal(event.sender, sender);
   return service.pull(sender, id);
  });
  ipcMain.handle('fixture:http-cancel', (event, id) => {
   assert.equal(event.sender, sender);
   return service.cancel(sender, id);
  });
  ipcMain.handle('fixture:http-dispose', (event, id) => {
   assert.equal(event.sender, sender);
   return service.dispose(sender, id);
  });
  let firstResolve, canceledResolve;
  const firstReport = new Promise(resolve => {firstResolve = resolve;});
  const canceledReport = new Promise(resolve => {canceledResolve = resolve;});
  ipcMain.on('fixture:report', (event, report) => {
   assert.equal(event.sender, sender);
   if (report.stage === 'first' || report.stage === 'error') firstResolve(report);
   if (report.stage === 'canceled' || report.stage === 'error') canceledResolve(report);
  });
  await rendererWindow.loadFile(path.join(fixtureRoot, 'tests/iab_http_renderer.html'), {
   query: {module: pathToFileURL(path.join(process.env.LCU_TEST_RELEASE,
    'lcu/host/oauth-renderer.js')).href},
  });
  const firstOverIpc = await Promise.race([firstReport,
   new Promise((_resolve, reject) => setTimeout(() => reject(Error('BrowserWindow first chunk timed out')), 5000))]);
  assert.deepEqual(firstOverIpc, {stage: 'first', done: false, chunk: 'first chunk'});
  sender.send('fixture:continue');
  const canceledOverIpc = await Promise.race([canceledReport,
   new Promise((_resolve, reject) => setTimeout(() => reject(Error('BrowserWindow cancellation timed out')), 5000))]);
  assert.deepEqual(canceledOverIpc, {stage: 'canceled'});
  await assert.rejects(service.pull(sender, 'browser-window-stream'), /unavailable/);
  rendererWindow.destroy();
  owner.destroy();
  await assert.rejects(service.fetch(owner, 'after-destroy', {url: 'https://fixture.example/ok',
   method: 'GET', headers: {}}), /destroyed/);
  service.disposeAll();
  console.log(JSON.stringify({originalFetchWrapper: 'PASS', originalWindowProvider: 'PASS',
   networkPolicy: 'PASS', errorRecovery: 'PASS', cancellation: 'PASS',
   earlyChunk: 'PASS', rendererEarlyChunk: 'PASS', browserWindowIpcStream: 'PASS',
   streamCancellation: 'PASS',
   ownerLifetime: 'PASS',
   authenticatedOAuth: 'NOT EXERCISED'}));
 } catch (error) {console.error(error.stack); process.exitCode = 1;}
 finally {app.exit(process.exitCode || 0);}
});
