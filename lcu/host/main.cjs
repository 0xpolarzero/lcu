// Local window/stdio integration for the unchanged original Codex IAB host.
const path = require('node:path');
const fs = require('node:fs');
const {randomUUID} = require('node:crypto');
const {pathToFileURL} = require('node:url');
const readline = require('node:readline');
const {app, BrowserWindow, Menu, webContents, ipcMain, protocol, net, nativeTheme} = require('electron');
protocol.registerSchemesAsPrivileged([{scheme:'lcu-assets',privileges:{standard:true,secure:true,supportFetchAPI:true,corsEnabled:true}}]);
const root = path.resolve(__dirname, '../..');
process.env.LCU_APPLICATION_PATH ||= path.join(root, 'host/application');
const generated = process.env.LCU_IAB_PROVIDER_PATH || path.join(root, 'host/iab/provider.cjs');
const {BrowserHost, BrowserSessionRegistry, createCommentModePolicy, createSiteBootstrap, FeatureOverridesSchema, getFeatures, normalizeFeatures, updateFeatures, RuntimeMessageSchema, isBrowserPageEvent, siteToolsEvent, siteAnnotationsEvent, dispatchBrowserRuntimeMessage,dispatchAnnotationMessage,dispatchBrowserCommand,browserFindMenuAccelerators,parseRendererPopupFrame,popupWindowSurfaceOptions,popupWindowColors,DesktopSettingsService,PersistedAtomHost,readAccountInfo,isCopilotApiAvailable} = require(generated);
const originalShared=require(path.join(process.env.LCU_APPLICATION_PATH,'resources/app.asar/.vite/build/src-C3YaUE83.js'));
const {resolveRuntimeIntl}=require('./locale.cjs');
const {ApplicationNetwork,_:parseDeepLink} = require(path.join(path.dirname(generated), 'bootstrap-provider.cjs'));
const args = process.argv.slice(2);
const sessionIdIndex = args.indexOf('--session-id');
const initialSessionId = sessionIdIndex < 0 ? null : args[sessionIdIndex + 1];
const owners = new Map();
const popupCreatedListeners = new Set();
const notificationListeners = new Set();
const appServerNotifications = {registerInternalNotificationHandler(handler) {notificationListeners.add(handler);return () => notificationListeners.delete(handler);}};
let host, registry, settings, rendererSettings, persistedAtoms, httpService, accountContext, shuttingDown = false;
let runtimeIntlConfig;
const buildFlavor=process.env.BROWSER_USE_CODEX_APP_BUILD_FLAVOR||'prod';
let featurePolicy={desktop:{},annotationApi:{enabled:false,permissionRequired:true},tweaks:false,annotationMultiSelect:false};
function applyFeatures(input) {
 if(!input||typeof input!=='object'||Array.isArray(input))throw Error('Browser feature policy must be an object');
 if(Object.keys(input).some(key=>!['desktop','annotationApi','tweaks','annotationMultiSelect'].includes(key)))throw Error('Unknown browser feature policy field');
 const next={...featurePolicy,...input,desktop:{...featurePolicy.desktop,...(input.desktop||{})}};
 next.desktop=FeatureOverridesSchema.parse(next.desktop);
 if(!next.annotationApi||typeof next.annotationApi.enabled!=='boolean'||typeof next.annotationApi.permissionRequired!=='boolean'||Object.keys(next.annotationApi).some(key=>!['enabled','permissionRequired'].includes(key))||typeof next.tweaks!=='boolean'||typeof next.annotationMultiSelect!=='boolean')throw Error('Invalid browser host feature policy');
 updateFeatures(normalizeFeatures(next.desktop,{buildFlavor}));
 host.setTweaksFeatureEnabled(next.tweaks);
 host.setAnnotationMultiSelectFeatureEnabled(next.annotationMultiSelect);
 host.setSiteAnnotationApiFeatureEnabled(next.annotationApi.enabled,next.annotationApi.permissionRequired);
 featurePolicy=next;
 return {desktop:getFeatures(),annotationApi:next.annotationApi,tweaks:next.tweaks,annotationMultiSelect:next.annotationMultiSelect};
}
const pendingAppServerRequests=new Map();
const pendingOAuthOperations=new Map();
function requestAppServer(method,params,timeoutMs=30000) {
 const requestId=randomUUID();
 return new Promise((resolve,reject)=>{
  const timer=setTimeout(()=>{pendingAppServerRequests.delete(requestId);reject(Error('Original app-server bridge request timed out'));},timeoutMs);
  timer.unref();
  pendingAppServerRequests.set(requestId,{resolve,reject,timer});
  report({type:'app-server-request',requestId,method,params});
 });
}
const authClient=require('./auth.cjs')(path.dirname(generated),requestAppServer,message=>{
 for(const record of owners.values())if(!record.window.webContents.isDestroyed())record.window.webContents.send('lcu-iab:message',message);
});
const network = new ApplicationNetwork();
network.observeSessions();
function report(value) { process.stdout.write(JSON.stringify({lcuHost: value.type, ...value, type: undefined}) + '\n'); }
function validSessionId(value) {
 if (typeof value !== 'string' || !value || value.length > 4096 || value.includes('\0')) throw Error('A nonempty actual session ID is required');
 return value;
}
function recordForOwner(webContents) {
 return [...owners.values()].find(record => record.window.webContents === webContents);
}
function routeFromMessage(record, message) {
 if (message.conversationId !== record.sessionId || typeof message.browserTabId !== 'string') throw Error('Browser route does not belong to this session owner');
 return {conversationId: record.sessionId, browserTabId: message.browserTabId};
}
function syncView(record, route, observation = {}) {
 const thread = host.getThreadState(record.window.webContents, route.conversationId, route.browserTabId);
 if (!thread) throw Error('Original browser thread is missing');
 host.sync(record.window.webContents, {...route, hostKind:'right-panel', mountGeneration:0,
  presented:observation.visible ?? thread.presented, visible:observation.visible ?? thread.visible,
  bounds:observation.bounds ?? thread.bounds, viewportScale:1,
  isAgentControllingBrowser:thread.isBrowserUseActive === true,
  annotationModeEnabled:thread.isAnnotationModeEnabled,
  runtimeIntlConfig:observation.runtimeIntlConfig??thread.runtimeIntlConfig??runtimeIntlConfig, themeVariant:thread.themeVariant,
  emulatedViewportSize:thread.emulatedViewportSize, cwd:process.cwd()});
}
function visibleBrowserRoute(record) {
 if (!host || record.window.isDestroyed()) return null;
 const routes=[...record.generations.keys()].filter(browserTabId=>{
  const thread=host.getThreadState(record.window.webContents,record.sessionId,browserTabId);
  return thread?.hostKind==='right-panel'&&thread.visible===true&&thread.presented===true&&thread.page!=null;
 });
 return routes.length===1?{conversationId:record.sessionId,browserTabId:routes[0]}:null;
}
function appShellShortcutState(record) {
 const original=record.shellShortcutState??null;
 const route=visibleBrowserRoute(record);
 if(!route)return original;
 // This standalone window contains one actual original right-panel browser tab.
 // Report its observed route to the original _U/vU/yU shortcut resolver.
 return {...original,focusArea:original?.focusArea??'right-panel',rightPanelBrowserCanZoom:true,
  rightPanelBrowserConversationId:route.conversationId,rightPanelBrowserTabId:route.browserTabId,
  rightPanelCanCloseActiveTab:true};
}
const windowManager = {
 applicationNetwork: network,
 shouldSyncPersistedAtom(){return true;}, // Every registered LCU owner is a browser window, never an avatar overlay.
 sendMessageToAllWindows(message){for(const record of owners.values())this.sendMessageToWebContents(record.window.webContents,message);},
 sendMessageToWindow(window,message){this.sendMessageToWebContents(window.webContents,message);},
 addBrowserCommentPopupWindowCreatedHandler(handler) { popupCreatedListeners.add(handler); return () => popupCreatedListeners.delete(handler); },
 getPrimaryWindows() { return [...owners.values()].map(record => record.window).filter(window => !window.isDestroyed()); },
 getHostIdForWebContents(webContents) { return recordForOwner(webContents) ? 'local' : null; },
 getAppShellShortcutState(webContentsId) {
  const record=[...owners.values()].find(item=>!item.window.isDestroyed()&&item.window.webContents.id===webContentsId);
  return record?appShellShortcutState(record):null;
 },
 showWindow(window) { if (!window.isDestroyed()) window.show(); },
 queueCodexDeepLinkUrl(url) {
  const live=[...owners.values()].filter(record=>!record.window.isDestroyed());
  if(live.length!==1){report({type:'error',message:'In-app OAuth redirect has no unique standalone owner'});return false;}
  const route=parseDeepLink(url);
  if(route?.kind!=='connectorOAuthCallback'){report({type:'error',message:'In-app deep-link route has no standalone application handler'});return false;}
  return live[0].deepLinks.queueCodexDeepLinkUrl(url);
 },
 sendMessageToWebContents(webContents, message) {
  if (webContents.isDestroyed()) return;
  const record = recordForOwner(webContents);
  if (!record) throw Error('Original host addressed an unknown standalone window');
  if(message.type==='close-active-app-shell-tab'&&message.panelId==='right') {
   const route=visibleBrowserRoute(record);
   if(route)host.closePage(webContents,route.conversationId,route.browserTabId);
   return;
  }
  if (message.type === 'open-browser-tab') {
   const route = routeFromMessage(record, message);
   message = {...message,cwd:host.getThreadState(webContents,route.conversationId,route.browserTabId)?.cwd??process.cwd()};
   if(!record.permissions.has(route.browserTabId)) {
    const callback=new originalShared.wf(prompts=>{
     if(!webContents.isDestroyed())webContents.send('lcu-iab:message',{type:'lcu-permission-prompts',...route,prompts});
    });
    const subscription=host.permissionPrompts.subscribe(webContents,route,callback);
    record.permissions.set(route.browserTabId,{subscription,callback});
   }
  }
  if(message.type==='close-browser-tab'||message.type==='browser-sidebar-destroy-webview') {
   const subscribed=record.permissions.get(message.browserTabId);
   subscribed?.subscription[Symbol.dispose]();subscribed?.callback[Symbol.dispose]();record.permissions.delete(message.browserTabId);
  }
  if (message.type === 'browser-sidebar-browser-use-state') syncView(record, routeFromMessage(record, message));
  if (message.type === 'toggle-browser-panel' || message.type === 'browser-sidebar-open-panel-without-animation') {
   if (message.open === false) record.window.hide(); else record.window.show();
  }
  webContents.send('lcu-iab:message', message);
 }
};
async function addSession(sessionId, requestId) {
 validSessionId(sessionId);
 await app.whenReady();
 if (!owners.has(sessionId)) {
  const window = new BrowserWindow({show: false, width: 1280, height: 800, webPreferences: {
   preload: path.join(__dirname, 'preload.cjs'), contextIsolation: true, nodeIntegration: false, sandbox: true, webviewTag: true
  }});
  let resolveReady;
  const rendererReady = new Promise(resolve => { resolveReady = resolve; });
  const record = {window, sessionId, rendererId: randomUUID(), generations: new Map(), permissions:new Map(), resolveReady};
  owners.set(sessionId, record);
  record.deepLinks=require('./deep-links.cjs')(path.dirname(generated),{
   initialArgv:[],
   errorReporter:{reportNonFatal:error=>report({type:'nonfatal',message:error.message})},
   getPrimaryWindow:()=>window.isDestroyed()?null:window,
   ensurePrimaryWindowVisible:()=>{if(window.isDestroyed())return null;window.show();return window;},
   navigateToRoute:(ownerWindow,route)=>{
    if(window.isDestroyed())throw Error('Deep-link owner window is closed');
    if(ownerWindow!==window||route.kind!=='connectorOAuthCallback')throw Error('Original deep-link route has no standalone application handler');
    ownerWindow.show();
    ownerWindow.webContents.send('lcu-iab:message',{type:'connector-oauth-callback',fullRedirectUrl:route.fullRedirectUrl,returnTo:route.returnTo??undefined});
   }
  });
  for(const name of ['focus','blur'])window.on(name,()=>window.webContents.send('lcu-iab:message',{type:'electron-window-focus-changed',isFocused:name==='focus'}));
  window.webContents.setWindowOpenHandler(({url,frameName})=> {
   const popup=parseRendererPopupFrame(frameName);
   if(url!=='about:blank'||!popup||popup.conversationId!==sessionId||!record.generations.has(popup.browserTabId))return {action:'deny'};
   const surface={appearance:'browserCommentPopup',opaqueWindowSurfaceEnabled:false,platform:process.platform};
   const {backgroundColor,backgroundMaterial}=popupWindowColors({...surface,prefersDarkColors:nativeTheme.shouldUseDarkColors});
   return {action:'allow',outlivesOpener:false,overrideBrowserWindowOptions:{title:'',width:294,height:208,parent:window,show:false,backgroundColor,backgroundMaterial:backgroundMaterial??undefined,...popupWindowSurfaceOptions(surface),webPreferences:{contextIsolation:true,nodeIntegration:false,spellcheck:true,devTools:false}}};
  });
  window.webContents.on('did-create-window',(popup,details)=>{
   const route=parseRendererPopupFrame(details.frameName);
   if(details.url!=='about:blank'||!route||route.conversationId!==sessionId){popup.destroy();return;}
   popup.setMenuBarVisibility(false);popup.setVisibleOnAllWorkspaces(false);popup.hide();
   for(const callback of popupCreatedListeners)callback({...route,hostId:'local',owner:window.webContents,window:popup});
  });
  window.webContents.on('will-navigate', event => event.preventDefault());
  const windowId = window.id;
  await window.loadFile(path.join(__dirname, 'index.html'));
  await rendererReady;
  host.ensureWindowState(window, window.webContents);
  // Original zZe cleanup must still resolve this owner while its closed listener runs.
  window.on('closed', () => { for(const entry of record.permissions.values()){entry.subscription[Symbol.dispose]();entry.callback[Symbol.dispose]();}record.permissions.clear();for(const entry of record.settingSubscriptions?.values()||[]){entry.subscription[Symbol.dispose]();entry.callback[Symbol.dispose]();}registry.handleWindowClosed(windowId); owners.delete(sessionId); report({type:'session-closed',sessionId}); });
  host.registerWebviewHostSession(window.webContents, record.rendererId);
  registry.captureSessionRoute({conversationId: sessionId, owner: window.webContents});
  registry.setBrowserUseNativePipeEnabled(true);
 }
 const backend = registry.backendStatesBySessionId.get(sessionId);
 await backend?.starting;
 if (!backend?.server) throw Error('Original browser backend failed to start');
 report({type: 'session', requestId, sessionId, pipePath: backend.server.pipePath, profilePath:app.getPath('userData')});
}
// Original browser-page preload channels, with the original schema/dispatch and
// the same main-frame event restrictions as the original global app initializer.
function ownedPage(event) {
 const window=BrowserWindow.fromWebContents(event.sender);
 if(!window || !recordForOwner(window.webContents))return false;
 return host?.findPageStateForRuntimeSender(event.sender)!=null;
}
ipcMain.handle('codex_desktop:browser-sidebar-runtime-message', async (event,message)=>{
 const parsed=RuntimeMessageSchema.safeParse(message);
 if(!parsed.success || !ownedPage(event))return;
 await dispatchBrowserRuntimeMessage.call({browserHostManager:host},event.sender,parsed.data);
});
ipcMain.on('codex_desktop:browser-page-event', (event,message)=>{
 if(!isBrowserPageEvent(message) || !ownedPage(event))return;
 if(message.type===siteToolsEvent.type || message.type===siteAnnotationsEvent.type) {
  const frame=event.sender.mainFrame;
  if(event.processId!==frame.processId || event.frameId!==frame.routingId)return;
 }
 host.handlePageEvent(event.sender,message);
});
// Renderer messages describe actual mounted views; the original host checks route,
// renderer generation, native webContents ownership, navigation and downloads.
ipcMain.handle('lcu-iab:ready', event => {
 const record=recordForOwner(event.sender);
 if (!record || event.senderFrame !== event.sender.mainFrame) throw Error('Unknown renderer');
 record.resolveReady();
});
ipcMain.handle('lcu-iab:permission', (event,message)=>{
 if(!recordForOwner(event.sender)||event.senderFrame!==event.sender.mainFrame)throw Error('Unknown renderer');
 if(message.operation==='respond')return host.permissionPrompts.respond(event.sender,message.target,message.response);
 if(message.operation==='settings')return host.permissionPrompts.openSystemSettings(event.sender,message.target);
 throw Error('Unknown permission operation');
});
ipcMain.handle('lcu-iab:annotation',async(event,message)=>{
 const record=recordForOwner(event.sender);
 if(!record||event.senderFrame!==event.sender.mainFrame)throw Error('Unknown annotation renderer');
 if(message.conversationId!==record.sessionId)throw Error('Unknown annotation conversation');
 if(message.browserTabId!=null&&!record.generations.has(message.browserTabId))throw Error('Unknown annotation tab');
 if(message.type==='focus')return host.handleCommentOverlayFocus(event.sender,message.conversationId,message.browserTabId,message.sessionId);
 return dispatchAnnotationMessage.call({browserHostManager:host},event.sender,message);
});
ipcMain.handle('lcu-iab:command',async(event,message)=>{
 const record=recordForOwner(event.sender);
 if(!record||event.senderFrame!==event.sender.mainFrame)throw Error('Unknown browser command renderer');
 routeFromMessage(record,message);
 if(message.type!=='browser-sidebar-command'||message.command==null||typeof message.command.type!=='string')throw Error('Invalid original browser command');
 if(message.command.type==='navigate'&&message.command.hostId!=null&&message.command.hostId!=='local')throw Error('Remote browser navigation has no owned standalone host');
 return dispatchBrowserCommand.call({browserHostManager:host,appServerConnectionRegistry:{getConnection:hostId=>hostId==='local'?authClient:null},getHostConfigForHostId:()=>null},event.sender,message);
});
ipcMain.handle('lcu-iab:shortcut-state',(event,state)=>{
 const record=recordForOwner(event.sender);
 if(!record||event.senderFrame!==event.sender.mainFrame)throw Error('Unknown app-shell state renderer');
 if(state==null||typeof state!=='object'||Array.isArray(state)||!['main','bottom-panel','right-panel',null].includes(state.focusArea??null))throw Error('Invalid original app-shell shortcut state');
 record.shellShortcutState=state;
});
ipcMain.handle('lcu-iab:page-command',(event,message)=>{
 const record=recordForOwner(event.sender);
 if(!record||event.senderFrame!==event.sender.mainFrame)throw Error('Unknown browser page command renderer');
 routeFromMessage(record,message);
 if(!message.command||!['open-find','set-find-query','find-next','find-previous','close-find'].includes(message.command.type))throw Error('Invalid original page command');
 return host.runPageCommand(event.sender,message);
});
ipcMain.handle('lcu-iab:browser-host',(event,message)=>{
 const record=recordForOwner(event.sender);
 if(!record||event.senderFrame!==event.sender.mainFrame)throw Error('Unknown browser renderer');
 if(message.operation==='register-session'){
  if(typeof message.rendererInstanceId!=='string'||!message.rendererInstanceId)throw Error('Invalid renderer session');
  const registered=host.registerWebviewHostSession(event.sender,message.rendererInstanceId);
  if(registered)record.rendererId=message.rendererInstanceId;
  return registered;
 }
 if(message.operation==='register-host'){
  routeFromMessage(record,message);
  if(typeof message.hostGeneration!=='number'||!Number.isInteger(message.hostGeneration)||message.hostGeneration<1||typeof message.rendererInstanceId!=='string')throw Error('Invalid browser host generation');
  const registered=host.registerWebviewHost(event.sender,message.browserTabId,message.conversationId,message.hostGeneration,message.pagePersistence,message.rendererInstanceId);
  if(registered)record.generations.set(message.browserTabId,message.hostGeneration);
  return registered;
 }
 if(message.operation==='sync-view'){
  routeFromMessage(record,message.state);
  return host.syncView(event.sender,message.state);
 }
 if(message.operation==='annotation-presentation'){
  routeFromMessage(record,message.state);
  return host.setAnnotationPresentation(event.sender,message.state);
 }
 throw Error('Unknown original browser host operation');
});
ipcMain.handle('lcu-iab:persisted',async(event,message)=>{
 if(!recordForOwner(event.sender)||event.senderFrame!==event.sender.mainFrame)throw Error('Unknown persisted-state renderer');
 if(message.type==='persisted-atom-sync-request')return persistedAtoms.sendPersistedAtomState(event.sender,message.responsePriority);
 if(message.type==='persisted-atom-update')return persistedAtoms.updatePersistedAtomState(event.sender,message.key,message.deleted?undefined:message.value,message.recordUpdate);
 throw Error('Unknown persisted-state operation');
});
ipcMain.handle('lcu-iab:account',async(event)=>{
 if(!recordForOwner(event.sender)||event.senderFrame!==event.sender.mainFrame)throw Error('Unknown account renderer');
 return accountContext.readAuthInputs();
});
ipcMain.handle('lcu-iab:account-info',async(event)=>{
 if(!recordForOwner(event.sender)||event.senderFrame!==event.sender.mainFrame)throw Error('Unknown account renderer');
 return accountContext.readAccountInfo();
});
ipcMain.handle('lcu-iab:intl',event=>{
 if(!recordForOwner(event.sender)||event.senderFrame!==event.sender.mainFrame)throw Error('Unknown locale renderer');
 return runtimeIntlConfig;
});
ipcMain.handle('lcu-iab:oauth-reply',(event,message)=>{
 const record=recordForOwner(event.sender);
 if(!record||event.senderFrame!==event.sender.mainFrame)throw Error('Unknown OAuth renderer');
 const pending=pendingOAuthOperations.get(message?.requestId);
 if(!pending||pending.sessionId!==record.sessionId||pending.owner!==event.sender)throw Error('Unknown OAuth operation');
 pendingOAuthOperations.delete(message.requestId);clearTimeout(pending.timer);
 report({type:'oauth-operation',requestId:message.requestId,sessionId:record.sessionId,operation:pending.operation,processed:!message.error,
  registered:pending.operation==='register'&&!message.error?typeof message.result==='string':undefined});
});
ipcMain.handle('lcu-iab:http-fetch',(event,message)=>{
 if(!recordForOwner(event.sender)||event.senderFrame!==event.sender.mainFrame)throw Error('Unknown HTTP renderer');
 return httpService.fetch(event.sender,message.requestId,message.request,message.trackUploadProgress===true);
});
ipcMain.handle('lcu-iab:http-cancel',(event,requestId)=>{
 if(!recordForOwner(event.sender)||event.senderFrame!==event.sender.mainFrame)throw Error('Unknown HTTP renderer');
 return httpService.cancel(event.sender,requestId);
});
ipcMain.handle('lcu-iab:http-pull',(event,requestId)=>{
 if(!recordForOwner(event.sender)||event.senderFrame!==event.sender.mainFrame)throw Error('Unknown HTTP renderer');
 return httpService.pull(event.sender,requestId);
});
ipcMain.handle('lcu-iab:http-dispose',(event,requestId)=>{
 if(!recordForOwner(event.sender)||event.senderFrame!==event.sender.mainFrame)throw Error('Unknown HTTP renderer');
 return httpService.dispose(event.sender,requestId);
});
ipcMain.handle('lcu-iab:settings',async(event,message)=>{
 const record=recordForOwner(event.sender);
 if(!record||event.senderFrame!==event.sender.mainFrame)throw Error('Unknown settings renderer');
 if(message.operation==='readAll')return rendererSettings.readAll();
 if(message.operation==='subscribe'){
  const callback=new originalShared.wf(value=>event.sender.send('lcu-iab:message',{type:'lcu-setting',key:message.key,value}));
  const subscription=await rendererSettings.subscribe(message.key,callback);
  const id=randomUUID();record.settingSubscriptions??=new Map();record.settingSubscriptions.set(id,{subscription,callback});return id;
 }
 if(message.operation==='unsubscribe'){
  const item=record.settingSubscriptions?.get(message.id);item?.subscription[Symbol.dispose]();item?.callback[Symbol.dispose]();record.settingSubscriptions?.delete(message.id);return;
 }
 throw Error('Unknown settings operation');
});
ipcMain.handle('lcu-iab:assets', event => {
 if (!recordForOwner(event.sender) || event.senderFrame !== event.sender.mainFrame) throw Error('Unknown renderer');
 return 'lcu-assets://app/';
});
ipcMain.handle('lcu-iab:view', (event, message) => {
 const record = recordForOwner(event.sender);
 if (!record || event.senderFrame !== event.sender.mainFrame) return;
 try {
  const route = routeFromMessage(record, message);
  if (message.type === 'view') {
   syncView(record, route, message);
  } else if (message.type === 'destroyed') {
   host.browserWebviewDestroyed(event.sender, route.conversationId, route.browserTabId, message.teardownId);
  } else if (message.type === 'cursor-arrived') {
   registry.notifyBrowserUseCursorArrived({owner:event.sender,payload:{conversationId:message.sessionConversationId,moveSequence:message.moveSequence}});
  }
 } catch (error) { report({type:'error',message:error.message}); }
});
async function shutdown() {
 if (shuttingDown) return;
 shuttingDown = true;
 for (const id of registry?.backendStatesBySessionId.keys() || []) await registry.disposeBackendForSession(id);
 for (const record of [...owners.values()]) if (!record.window.isDestroyed()) record.window.destroy();
 await settings?.dispose();
 authClient.invalidate();authClient.disposed=true;
 httpService?.disposeAll();
 for(const pending of pendingAppServerRequests.values()){clearTimeout(pending.timer);pending.reject(Error('Original host stopped'));}pendingAppServerRequests.clear();
 for(const pending of pendingOAuthOperations.values())clearTimeout(pending.timer);pendingOAuthOperations.clear();
 network.dispose();
 app.quit();
}
app.on('window-all-closed', () => {});
app.whenReady().then(() => {
 runtimeIntlConfig=resolveRuntimeIntl(process.env.LCU_BROWSER_RUNTIME_INTL_PATH?JSON.parse(fs.readFileSync(process.env.LCU_BROWSER_RUNTIME_INTL_PATH,'utf8')):null,app.getLocale());
 protocol.handle('lcu-assets',request=>{
  const url=new URL(request.url),name=decodeURIComponent(url.pathname).replace(/^\//,'');
  if(url.hostname!=='app'||!name||name.includes('..')||name.includes('\\'))return new Response('Invalid asset',{status:403});
  const derived=path.join(path.dirname(generated),'renderer',name);
  const source=fs.existsSync(derived)?derived:path.join(process.env.LCU_APPLICATION_PATH,'resources/app.asar/webview/assets',name);
  return net.fetch(pathToFileURL(source).href);
 });
 // The original annotation screenshot path reports capture failures as
 // nonfatal after saving the comment. Keep that severity across the bridge.
 const errorReporter = {reportNonFatal(error,context) { report({type:'nonfatal',message:error.message,kind:context?.kind}); }};
 registry = new BrowserSessionRegistry(randomUUID(), buildFlavor, errorReporter);
 settings=require('./settings.cjs')(path.dirname(generated),requestAppServer);
 accountContext=require('./account-context.cjs')({authClient,globalState:settings.globalState,
  readOriginalAccountInfo:()=>readAccountInfo({getConnection:hostId=>{
   if(hostId!=='local')throw Error('Unknown account host');
   return authClient;
  }}),isCopilotApiAvailable});
 httpService=require('./http-service.cjs')(path.dirname(generated),{applicationNetwork:network,authClient,globalState:settings.globalState,originalShared,buildFlavor});
 rendererSettings=new DesktopSettingsService(settings.store,()=>{},undefined);
 host = new BrowserHost(windowManager, errorReporter, undefined, createCommentModePolicy({appServerClient:authClient}), registry, undefined, {...settings.options,getSiteBootstrapToken:createSiteBootstrap(authClient),appServerNotificationSource:appServerNotifications,browserPersistenceDirectory:app.getPath('userData')});
 // The original menu reserves these accelerators for the original focused-page
 // command path; DGe deliberately lets Find/Next/Previous reach the menu.
 const menuCommand=type=>{
  const owner=BrowserWindow.getFocusedWindow(),focused=webContents.getFocusedWebContents();
  if(owner&&!owner.isDestroyed()&&recordForOwner(owner.webContents)&&focused&&host.runFocusedVisiblePageCommand(owner,focused,{type}))return;
  const target=owner&&!owner.isDestroyed()&&recordForOwner(owner.webContents)?owner:windowManager.getPrimaryWindows().find(window=>window.isVisible());
  if(target)windowManager.sendMessageToWindow(target,{type:{'open-find':'find-in-thread','find-next':'find-next-in-thread','find-previous':'find-previous-in-thread'}[type]});
 };
 const closeFocusedTab=()=>{
  const owner=BrowserWindow.getFocusedWindow(),focused=webContents.getFocusedWebContents();
  if(owner&&!owner.isDestroyed()&&recordForOwner(owner.webContents)&&focused)host.closeFocusedVisibleBrowserTab(owner,focused);
 };
 const [find,findNext,findPrevious]=browserFindMenuAccelerators(process.platform==='darwin');
 const closeTitle=originalShared.Mt({commandId:'closeTab'})?.menuTitle;
 const findTitle=originalShared.Mt({commandId:'findInThread'})?.menuTitle;
 if(!closeTitle||!findTitle)throw Error('Original browser menu commands are unavailable');
 const closeItems=host.ownerCommandAccelerators.closeTab.filter(accelerator=>!accelerator.includes(' ')).map(accelerator=>({label:closeTitle,accelerator,click:closeFocusedTab}));
 Menu.setApplicationMenu(Menu.buildFromTemplate([{label:'Edit',submenu:[
  {label:findTitle,accelerator:find,click:()=>menuCommand('open-find')},
  {label:'Find Next',accelerator:findNext,click:()=>menuCommand('find-next')},
  {label:'Find Previous',accelerator:findPrevious,click:()=>menuCommand('find-previous')},
  ...closeItems,
 ]}]));
 settings.connectHost(host);
 persistedAtoms=Object.assign(new PersistedAtomHost(),{globalState:settings.globalState,browserHostManager:host,windowManager,
  chunkedMessageSender:{sendCritical:(owner,_channel,message)=>windowManager.sendMessageToWebContents(owner,message)},
  sendMessageToView:(owner,message)=>windowManager.sendMessageToWebContents(owner,message)});
 // Caller-supplied host policy feeds original setters, without changing auth or
 // managed network requirements. Defaults resolve unavailable annotations safely.
 applyFeatures(process.env.LCU_BROWSER_FEATURES_PATH ? JSON.parse(fs.readFileSync(process.env.LCU_BROWSER_FEATURES_PATH,'utf8')) : {});
}).catch(error => { report({type:'error',message:error.message}); shutdown(); });
let commands = Promise.resolve(), initialRegistered = false;
const input = readline.createInterface({input:process.stdin});
input.on('line', line => {
 let message;
 try { message = JSON.parse(line); } catch { report({type:'error',message:'Invalid host bridge JSON'}); return; }
 // Invalidating is immediate, never delayed behind an outstanding view request.
 if(message.type==='app-server-response') {
  const pending=pendingAppServerRequests.get(message.requestId);
  if(!pending)return;
  pendingAppServerRequests.delete(message.requestId);clearTimeout(pending.timer);
  if(message.error)pending.reject(Error(typeof message.error==='string'?message.error:message.error.message||'Original app-server request failed'));
  else pending.resolve(message.result);
  return;
 }
 if (message.type === 'invalidate') { network.invalidate(); authClient.invalidate(); return; }
 commands = commands.then(async () => {
  if (message.type === 'requirements') {
   authClient.connect(message.appServerVersion);
   await network.refreshRequirements(message.appServerVersion, async () => message.configRequirements);
   await app.whenReady();
   await settings.initialize();
   if (!initialRegistered && initialSessionId) { initialRegistered = true; await addSession(initialSessionId); }
   report({type:'requirements-ready',requestId:message.requestId});
  } else if(message.type==='features') {
   report({type:'features',requestId:message.requestId,policy:applyFeatures(message.policy)});
  } else if(message.type==='intl') {
   runtimeIntlConfig=resolveRuntimeIntl(message.runtimeIntlConfig,app.getLocale());
   for(const record of owners.values())if(!record.window.isDestroyed())record.window.webContents.send('lcu-iab:message',{type:'lcu-intl',runtimeIntlConfig});
   report({type:'intl',requestId:message.requestId});
  } else if(message.type==='oauth-operation') {
   const record=owners.get(validSessionId(message.sessionId));
   if(!record||record.window.isDestroyed())throw Error('OAuth owner is unavailable');
   if(typeof message.requestId!=='string'||!message.requestId||pendingOAuthOperations.has(message.requestId))throw Error('Invalid OAuth operation ID');
   if(!['register','clear'].includes(message.operation)||message.params==null||typeof message.params!=='object'||Array.isArray(message.params))throw Error('Invalid OAuth operation');
   const timer=setTimeout(()=>{pendingOAuthOperations.delete(message.requestId);report({type:'oauth-operation',requestId:message.requestId,sessionId:record.sessionId,operation:message.operation,processed:false});},30000);
   timer.unref();pendingOAuthOperations.set(message.requestId,{sessionId:record.sessionId,owner:record.window.webContents,operation:message.operation,timer});
   record.window.webContents.send('lcu-iab:message',{type:'lcu-oauth-operation',requestId:message.requestId,operation:message.operation,params:message.params});
  } else if(message.type==='deep-link') {
   const record=owners.get(validSessionId(message.sessionId));
   if(!record||record.window.isDestroyed())throw Error('Deep-link owner is unavailable');
   const route=parseDeepLink(message.url);
   if(route?.kind!=='connectorOAuthCallback')throw Error('Only original connector OAuth callback routes have a standalone application handler');
   const accepted=record.deepLinks.queueCodexDeepLinkUrl(message.url);
   report({type:'deep-link',requestId:message.requestId,sessionId:message.sessionId,accepted:accepted===true});
  } else if (message.type === 'notification') {
   authClient.notify(message.notification);
   for (const handler of notificationListeners) handler(message.notification);
   if(message.notification?.method==='account/updated'||message.notification?.method==='account/login/completed')for(const record of owners.values())if(!record.window.isDestroyed())record.window.webContents.send('lcu-iab:message',{type:'lcu-account-updated'});
  } else if (message.type === 'session') await addSession(message.sessionId, message.requestId);
  else if (message.type === 'turn-ended') {
   const backend = registry.backendStatesBySessionId.get(validSessionId(message.sessionId));
   await backend?.apiImpl?.turnEnded({session_id:message.sessionId,turn_id:message.turnId});
  } else if (message.type === 'shutdown') await shutdown();
  else throw Error('Unknown host bridge command');
 }).catch(error => { report({type:'error',requestId:message.requestId,message:error.message}); });
});
input.on('close', shutdown);
process.on('SIGTERM', shutdown);
process.on('SIGINT', shutdown);
