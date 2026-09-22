// Test-only observation of the installed original host; actions use native input.
const assert = require('node:assert/strict');
const {BrowserWindow,Menu} = require('electron');
const {execFileSync} = require('node:child_process');
const provider = require(process.env.LCU_IAB_PROVIDER_PATH);
const OriginalHost = provider.BrowserHost;
const OriginalRegistry = provider.BrowserSessionRegistry;
let host, registry, originalFindEvents=[], findRouteEvents=[], forceNativeFindUnavailable=false;
provider.BrowserHost = class extends OriginalHost {
 constructor(...args) { super(...args); host = this; }
 runFocusedVisiblePageCommand(...args) {
  const accepted=forceNativeFindUnavailable&&args[2]?.type==='open-find'?false:super.runFocusedVisiblePageCommand(...args);
  if(forceNativeFindUnavailable&&args[2]?.type==='open-find')findRouteEvents.push({route:'native-menu',command:args[2]?.type,accepted});
  return accepted;
 }
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
function xdo(...args) {execFileSync('xdotool',args,{stdio:'pipe'});}
function chord(keyCode, modifiers='ctrl') {xdo('key','--clearmodifiers',modifiers?`${modifiers}+${keyCode}`:keyCode);}
function typeText(value) {xdo('type','--clearmodifiers','--delay','1',value);}
async function center(owner, selector) {
 const point=await owner.webContents.executeJavaScript(`(() => {
  const element=document.querySelector(${JSON.stringify(selector)});
  if(!element)return null;
  const rect=element.getBoundingClientRect();
  return {x:Math.round(rect.x+rect.width/2),y:Math.round(rect.y+rect.height/2),disabled:element.disabled};
 })()`);
 assert.ok(point, `Missing native input target ${selector}`);
 return point;
}
async function click(owner, selector) {
 const {x,y,disabled}=await center(owner,selector);
 assert.notEqual(disabled,true,`Disabled native input target ${selector}`);
 const bounds=owner.getBounds();
 xdo('mousemove','--sync',String(bounds.x+x),String(bounds.y+y),'click','1');
}
async function state(owner) {
 return owner.webContents.executeJavaScript(`({
  buttons:[...document.querySelectorAll('button')].map(b=>({label:b.getAttribute('aria-label'),disabled:b.disabled})).filter(b=>b.label),
  inputs:[...document.querySelectorAll('input')].map(i=>({placeholder:i.placeholder,value:i.value})),
  text:document.body.innerText.slice(0,500),
  webviews:document.querySelectorAll('webview').length,
 })`);
}
async function findDiagnostics(owner,thread) {
 const [ui,page]=await Promise.all([
  owner.webContents.executeJavaScript(`({active:document.activeElement?.outerHTML?.slice(0,300),inputs:[...document.querySelectorAll('input')].map(i=>({placeholder:i.placeholder,value:i.value,focused:i===document.activeElement})),text:document.body.innerText.slice(0,700),focusEvents:window.__lcuFindFocusEvents})`).catch(error=>({error:error.message})),
  thread.page?.view?.webContents?.executeJavaScript(`({url:location.href,title:document.title,text:document.body.innerText.slice(0,700),selection:getSelection()?.toString()})`).catch(error=>({error:error.message}))
 ]);
 let focus;
 try {focus=execFileSync('xdotool',['getwindowfocus','getwindowname'],{encoding:'utf8'}).trim();}
 catch(error) {focus=error.message;}
 return {nativeFocus:focus,ui,page,findState:thread.findState,originalFindEvents,findRouteEvents};
}
(async () => {
 try {
  const api=await until('original IAB backend',()=>[...registry?.backendStatesBySessionId?.values()||[]][0]?.apiImpl);
  const meta={session_id:'commands-fixture',turn_id:'commands-turn'};
  const tab=await api.createTab(meta),target={tabId:tab.id};
  const cdp=(method,commandParams={})=>api.executeCdp({...meta,target,method,commandParams});
  const base='http://127.0.0.1:9877/';
  await cdp('Page.navigate',{url:base}); // Deterministic initial state only.
  await until('initial fixture page',async()=>
   (await cdp('Runtime.evaluate',{expression:'location.pathname',returnByValue:true})).result?.value==='/');
  await api.executeUnhandledCommand({...meta,type:'browser_visibility_set',browser_id:'iab',visible:true});
  const owner=await until('owner window',()=>BrowserWindow.getAllWindows().find(w=>w.webContents.getURL().includes('/lcu/host/index.html')));
  const thread=await until('original browser thread',()=>[...host.windows.values()][0]?.threads?.values().next().value);
  await api.releaseSessionControl(api.getBrowserUseSession(meta));
  await until('user control',()=>thread.isBrowserUseActive===false);
  await until('mounted native webview',()=>state(owner).then(s=>s.webviews===1));
  owner.show();owner.focus();
  await click(owner,'input[placeholder="Search or enter a URL"]');
  chord('a');
  typeText(base+'next');
  chord('Return','');
  await until('native address navigation',()=>thread.page?.url===base+'next');
  assert.equal((await cdp('Runtime.evaluate',{expression:'location.pathname',returnByValue:true})).result.value,'/next');
  await click(owner,'button[aria-label="Back"]');
  await until('native Back',()=>thread.page?.url===base);
  await click(owner,'button[aria-label="Next"]');
  await until('native Next',()=>thread.page?.url===base+'next');
  const before=Number((await cdp('Runtime.evaluate',{expression:'document.querySelector("#loads").textContent',returnByValue:true})).result.value);
  await click(owner,'button[aria-label="Reload page"]');
  await until('native Reload',async()=>Number((await cdp('Runtime.evaluate',{expression:'document.querySelector("#loads")?.textContent',returnByValue:true})).result?.value)>before);
  await until('native Reload completion',()=>thread.page?.view?.webContents?.isLoadingMainFrame()===false);
  if(process.env.LCU_TEST_FIND_FALLBACK==='1') {
   await click(owner,'input[placeholder="Search or enter a URL"]');
   forceNativeFindUnavailable=true;
   const findMenu=Menu.getApplicationMenu().items.find(item=>item.label==='Edit').submenu.items.find(item=>/Find/i.test(item.label));
   findMenu.click();
   try { await until('header Find fallback',()=>owner.webContents.executeJavaScript('document.activeElement?.id==="content-search-input"')); }
   catch(error) { error.findDiagnostics=await findDiagnostics(owner,thread); throw error; }
   assert.equal(findRouteEvents.at(-1)?.accepted,false,'Header Find should take the original renderer fallback: '+JSON.stringify(findRouteEvents.at(-1)));
   process.stdout.write(JSON.stringify({lcuHost:'fixture-done',fallback:'PASS',findRouteEvents})+'\n');
   return;
  }
  thread.page?.view?.webContents?.on('found-in-page',(_event,result)=>originalFindEvents.push({
   activeMatchOrdinal:result.activeMatchOrdinal,matches:result.matches,finalUpdate:result.finalUpdate,requestId:result.requestId,
  }));
  for(const [label,contents] of [['owner',owner.webContents],['page',thread.page?.view?.webContents]]) {
   if(!contents)continue;
   for(const event of ['focus','blur'])contents.on(event,()=>findRouteEvents.push({route:'web-contents-event',target:label,event,time:Date.now()}));
  }
  await owner.webContents.executeJavaScript(`(() => {
   window.__lcuFindFocusEvents=[];
   const note=(type,extra={})=>window.__lcuFindFocusEvents.push({type,time:Date.now(),active:document.activeElement?.tagName,activeId:document.activeElement?.id,...extra});
   document.addEventListener('keydown',event=>{if((event.ctrlKey||event.metaKey)&&event.key.toLowerCase()==='f')note('keydown-ctrl-f')},true);
   document.addEventListener('focusin',event=>note('focusin',{target:event.target?.tagName,id:event.target?.id}),true);
   document.addEventListener('focusout',event=>note('focusout',{target:event.target?.tagName,id:event.target?.id}),true);
  })()`);
  await click(owner,'webview');
  chord('f');
  await until('native Find',()=>state(owner).then(s=>s.inputs.some(i=>/find/i.test(i.placeholder))));
  try { await until('focused native Find input',()=>owner.webContents.executeJavaScript(`(() => {const input=[...document.querySelectorAll('input')].find(i=>/find/i.test(i.placeholder));return input&&input===document.activeElement})()`)); }
  catch(error) { error.findDiagnostics=await findDiagnostics(owner,thread); throw error; }
  typeText('needle');
  try { await until('native Find matches',()=>thread.findState?.matches===3); }
  catch(error) { error.findDiagnostics=await findDiagnostics(owner,thread); throw error; }
  await until('original visible Find counter',()=>state(owner).then(s=>s.text.includes('1 / 3 results')));
  await click(owner,'button[aria-label="Close find"]');
  await until('closed original Find surface',()=>state(owner).then(s=>!s.inputs.some(i=>/find/i.test(i.placeholder))));
  await click(owner,'webview');
  chord('w');
  await until('native Close',async()=>{
   const tabs=await api.getTabs(meta);
   return tabs.length===0;
  });
  assert.equal(await owner.webContents.executeJavaScript('document.querySelectorAll("webview").length'),0);
  process.stdout.write(JSON.stringify({lcuHost:'fixture-done',address:'PASS',back:'PASS',next:'PASS',reload:'PASS',find:'PASS',close:'PASS',findRouteEvents,focusEvents:await owner.webContents.executeJavaScript('window.__lcuFindFocusEvents')})+'\n');
 } catch(error) {
  process.stderr.write(`COMMAND FIXTURE FAILURE ${error.stack}\n${error.findDiagnostics?`FIND DIAGNOSTICS ${JSON.stringify(error.findDiagnostics)}\n`:''}`);
  process.stdout.write(JSON.stringify({lcuHost:'fixture-failed',message:error.message})+'\n');
 }
})();
