// Exercises the original annotation editor and guest marker against an offline page.
const assert = require('node:assert/strict');
const {app, BrowserWindow} = require('electron');
const provider = require(process.env.LCU_IAB_PROVIDER_PATH);
const OriginalHost = provider.BrowserHost;
const OriginalRegistry = provider.BrowserSessionRegistry;
const originalDispatchAnnotation = provider.dispatchAnnotationMessage;
let annotationRequestsStarted = 0, annotationRequestsPending = 0;
provider.dispatchAnnotationMessage = async function(...args) {
 annotationRequestsStarted++;
 annotationRequestsPending++;
 try { return await originalDispatchAnnotation.apply(this, args); }
 finally { annotationRequestsPending--; }
};
let host, registry;
provider.BrowserHost = class extends OriginalHost {
 constructor(...args) { super(...args); host = this; }
};
provider.BrowserSessionRegistry = class extends OriginalRegistry {
 constructor(...args) { super(...args); registry = this; }
};
require(process.env.LCU_TEST_ORIGINAL_HOST_MAIN);

const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
async function until(label, predicate, timeoutMs = 10000) {
 const deadline = Date.now() + timeoutMs;
 while (Date.now() < deadline) {
  const value = await predicate();
  if (value) return value;
  await sleep(50);
 }
 throw Error(`Timed out waiting for ${label}`);
}

(async () => {
 try {
  const state = await until('original IAB backend', () =>
   [...registry?.backendStatesBySessionId?.values() || []][0]?.apiImpl);
  const api = state, meta = {session_id: 'annotation-fixture', turn_id: 'annotation-turn'};
  const tab = await api.createTab(meta);
  const target = {tabId: tab.id};
  const cdp = (method, commandParams = {}) => api.executeCdp({...meta, target, method, commandParams});
  const url = 'http://127.0.0.1:9876/';
  const navigation = await cdp('Page.navigate', {url});
  assert.ok(!navigation.errorText, navigation.errorText);
  await until('offline page', async () =>
   (await cdp('Runtime.evaluate', {expression: 'document.title', returnByValue: true})).result?.value === 'Annotation fixture');
  await api.executeUnhandledCommand({...meta, type: 'browser_visibility_set', browser_id: 'iab', visible: true});
  const owner = await until('owner window', () => BrowserWindow.getAllWindows().find(w => w.webContents.getURL().includes('/lcu/host/index.html')));
  const thread = await until('original browser thread', () => [...host.windows.values()][0]?.threads?.values().next().value);
  await api.releaseSessionControl(api.getBrowserUseSession(meta));
  await until('agent control release', () => thread.isBrowserUseActive === false);
  await until('original webview attachment', () => owner.webContents.executeJavaScript('Boolean(document.querySelector("webview")?.getWebContentsId?.())'));
  const originalShared = require(process.env.LCU_APPLICATION_PATH + '/resources/app.asar/.vite/build/src-C3YaUE83.js');
  host.startCommentAtPoint(owner.webContents,
   {conversationId: 'annotation-fixture', browserTabId: thread.browserTabId},
   {x: 80, y: 25}, originalShared.$l.BATCH, 'context-menu', false);
  const popup = await until('original annotation popup', () => BrowserWindow.getAllWindows().find(w => w !== owner && !w.isDestroyed() && w.isVisible()));
  await until('original editor', () => popup.webContents.executeJavaScript('document.querySelectorAll("[contenteditable=true]").length === 1'));
  popup.focus();
  await popup.webContents.executeJavaScript('document.querySelector("[contenteditable=true]").focus()');
  const body = 'LCU original comment proof';
  for (const letter of body) popup.webContents.sendInputEvent({type: 'char', keyCode: letter});
  await until('typed comment', () => popup.webContents.executeJavaScript('document.querySelector("[contenteditable=true]")?.textContent === "LCU original comment proof"'));
  await until('enabled original submit button', () => popup.webContents.executeJavaScript('document.querySelector("button[aria-label=Comment]")?.disabled === false'));
  const beforeSubmit = annotationRequestsStarted;
  await popup.webContents.executeJavaScript('document.querySelector("button[aria-label=Comment]").click()');
  await until('original annotation submission', () => annotationRequestsStarted > beforeSubmit);
  const comment = await until('original saved comment', () => thread.snapshot.comments.find(c => c.body === body));
  assert.equal(comment.anchor.pageUrl, url);
  assert.equal(comment.anchor.selector, 'html > body > h1');
  await until('original guest page marker', async () => {
   const result = await cdp('Runtime.evaluate', {
    expression: 'document.querySelector("#codex-browser-sidebar-comments-root")?.shadowRoot?.querySelectorAll("[data-browser-comment-marker=true]").length || 0',
    returnByValue: true,
   });
   return result.result?.value === 1;
  });
  assert.equal(popup.isVisible(), false);
  const panel=await owner.webContents.executeJavaScript('({panels:document.querySelectorAll(".lcu-browser-panel-slots").length,webviews:document.querySelectorAll("webview").length,back:!!document.querySelector("button[aria-label=Back]")})');
  assert.equal(panel.panels,1);
  assert.equal(panel.webviews,1);
  assert.equal(panel.back,true);
  // The saved comment appears before the original screenshot task completes.
  // Keep its owner alive until that task settles, then test host shutdown.
  await until('original annotation submission settled', () => annotationRequestsPending === 0);
  process.stdout.write(JSON.stringify({lcuHost: 'fixture-done', commentBody: body, markerCount: 1}) + '\n');
 } catch (error) {
  process.stderr.write(`ANNOTATION FIXTURE FAILURE ${error.stack}\n`);
  process.stdout.write(JSON.stringify({lcuHost: 'fixture-failed', message: error.message}) + '\n');
 }
})();
