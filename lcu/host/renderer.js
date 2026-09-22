// Local service wiring only. Original Codex modules own webviews, painting,
// capture surfaces, cursor animation/arrival, destruction and release behavior.
const assets = await window.lcuHost.assets();
for (const file of ['app-shared-11c21cbb0024.css','app-initial-19d25b9d212e.css','app-primary-d77f37ba49ff.css','button-ae789623973e.css']) {
 const link=document.createElement('link');link.rel='stylesheet';link.href=assets+file;document.head.appendChild(link);
}
const shared=await import(assets+'app-shared-81f4259020b8.js');
const cursorModule=await import(assets+'button-3b7641138a7c.js');
shared.Kd(); // PSe: original BrowserWebviewHost initializer.
cursorModule.a(); cursorModule.i(); cursorModule.n(); shared.jz(); // Original cursor dynamics and image.
const pages=new Map(), pending=new Map(), permissionSubscribers=new Map();
const initial=await import(assets+'app-initial-430deae5a13a.js');
const annotation=await import(assets+'tab-content-b70d652be669.js');
const primary=await import(assets+'app-primary-1ee15bca6237.js');
const oauth=await import('./oauth-renderer.js');
let runtimeIntlConfig=await window.lcuHost.intl();
const settingsListeners=new Map();
let accountState;
let accountRefreshVersion=0;
async function refreshAccount(){
 const version=++accountRefreshVersion;
 const {response,authMethod,useCopilotAuthIfAvailable,isCopilotApiAvailable}=await window.lcuHost.account();
 const auth=response==null?initial.lcuEmptyAccountState():initial.lcuMapAccountState(response,{
  isPersonalAccessTokenAuth:authMethod==='personalAccessToken',
  useCopilotAuthIfAvailable,isCopilotApiAvailable
 });
 // Original GYc reads account-info only for ChatGPT auth. That host query
 // invokes the original pT token-claim producer; token bytes stay in main.
 const chatgptAuth=auth.authMethod==='chatgpt'||auth.authMethod==='chatgptAuthTokens';
 let info;
 if(chatgptAuth)try{info=await window.lcuHost.accountInfo();}catch(error){console.error('Original account-info query failed',error);}
 const hasAccountIdentity=chatgptAuth||auth.authMethod==='personalAccessToken';
 if(version!==accountRefreshVersion)return;
 accountState={...auth,isLoading:false,isCopilotApiAvailable,
  userId:chatgptAuth?info?.userId??null:null,
  accountId:chatgptAuth?info?.accountId??null:null,
  email:hasAccountIdentity?auth.email??info?.email??null:null,
  planAtLogin:hasAccountIdentity?auth.planAtLogin??info?.plan??null:null,
  computeResidency:chatgptAuth?info?.computeResidency??null:null};
}
await refreshAccount();
initial.lcuSetServices({
 browserHost:{
  focusCommentOverlay:route=>window.lcuHost.annotation({...route,type:'focus'}),
  registerWebviewHostSession:({rendererInstanceId})=>window.lcuHost.browserHost({operation:'register-session',rendererInstanceId}),
  registerWebviewHost:state=>window.lcuHost.browserHost({operation:'register-host',...state}),
  syncView:state=>window.lcuHost.browserHost({operation:'sync-view',state}),
  setAnnotationPresentation:state=>window.lcuHost.browserHost({operation:'annotation-presentation',state})
  ,runPageCommand:message=>window.lcuHost.pageCommand(message)
  ,subscribePermissionPrompts(target,callback){
   const key=target.browserTabId;
   const listeners=permissionSubscribers.get(key)||new Set();listeners.add(callback);permissionSubscribers.set(key,listeners);
   callback(pages.get(key)?.prompts||pending.get(key)?.prompts||[]);
   return {[Symbol.dispose](){listeners.delete(callback);if(!listeners.size)permissionSubscribers.delete(key);}};
  },
  respondToPermissionPrompt:(target,response)=>window.lcuHost.permission({operation:'respond',target,response}),
  openPermissionSystemSettings:target=>window.lcuHost.permission({operation:'settings',target})
 },
 httpFetch:oauth.createHttpFetch(window.lcuHost),
 settings:{
  readAll:()=>window.lcuHost.settings({operation:'readAll'}),
  async subscribe(key,callback){
   const listeners=settingsListeners.get(key)||new Set();listeners.add(callback);settingsListeners.set(key,listeners);
   const id=await window.lcuHost.settings({operation:'subscribe',key});
   return {[Symbol.dispose](){listeners.delete(callback);window.lcuHost.settings({operation:'unsubscribe',id});}};
  }
 }
});
const annotationMount=document.createElement('div');document.body.append(annotationMount);
const annotationRoot=shared.OB().createRoot(annotationMount);
const panelMount=document.createElement('div');panelMount.id='browser-panel';document.body.append(panelMount);
const panelRoot=shared.OB().createRoot(panelMount);
class PanelBoundary extends initial.lcuOAuthReact.Component {
 constructor(props){super(props);this.state={error:null};}
 static getDerivedStateFromError(error){return {error};}
 componentDidCatch(error){const summary=(item,depth=0)=>({message:item.message,stack:item.stack?.split('\n').slice(0,3),errors:depth<4?item.errors?.map(nested=>summary(nested,depth+1)):undefined});console.error('Original browser panel mount failed',JSON.stringify(summary(error)));}
 render(){return this.state.error?null:this.props.children;}
}
const queryClient=initial.lcuCreateQueryClient();
let oauthReady;
const oauthMounted=new Promise(resolve=>{oauthReady=resolve;});
const OAuthOperations=oauth.createOAuthOperations(initial,{subscribe:listener=>window.lcuHost.subscribe(listener),reply:message=>window.lcuHost.oauthReply(message),onReady:oauthReady});
const h=initial.lcuOAuthReact.createElement;
function renderBrowserSlots({headerRows,content}) {
 return h('div',{className:'lcu-browser-panel-slots'},
  ...headerRows.map(row=>h('div',{key:row.id,className:'lcu-browser-panel-header'},row.content)),
  h('div',{className:'lcu-browser-panel-content'},content));
}
window.addEventListener('codex-message-from-view',event=>{if(event.detail?.type?.startsWith('persisted-atom-'))window.lcuHost.persisted(event.detail).catch(console.error);});
const hydrateAtoms=initial.lcuInitializePersistedAtoms();
function renderAnnotations(){
 const overlays=[];
 annotationRoot.render(shared.jB().jsx(shared.Mz,{...runtimeIntlConfig,children:shared.jB().jsx(initial.LcuReactQueryProvider,{client:queryClient,children:shared.jB().jsx(initial.LcuQueryScopeProvider,{queryClient,children:shared.jB().jsx(initial.kmn,{scope:initial.Ppn,children:shared.jB().jsx(initial.LcuOAuthAccountContext.Provider,{value:accountState,children:[shared.jB().jsx(OAuthOperations,{},'oauth'),...overlays]})})})})}));
 const panels=[...pages.values()].map(record=>h(initial.kmn,{scope:initial.LcuThreadScope,value:{clientThreadId:record.conversationId,routeConversationId:record.conversationId},key:record.browserTabId},
  h(initial.kmn,{scope:initial.LcuRouteScope,value:{routeKind:'local-thread',conversationId:record.conversationId,pathname:'/threads/'+encodeURIComponent(record.conversationId)}},
   h(initial.LcuAppShellLayout,null,
    h(annotation.LcuBrowserPanel,{...route(record),cwd:record.cwd,isVisible:record.visible,isAnnotationModeEnabled:record.snapshot?.interactionMode==='comment',renderSlots:renderBrowserSlots}),
    h(primary.LcuFindBar.Surface)))));
 panelRoot.render(h(initial.LcuResizeObserverProvider,null,h(initial.LcuMemoryRouter,{initialEntries:['/threads/'+encodeURIComponent(pages.values().next().value?.conversationId??'')]},h(PanelBoundary,null,h(shared.Mz,runtimeIntlConfig,h(initial.LcuReactQueryProvider,{client:queryClient},h(initial.LcuQueryScopeProvider,{queryClient},h(initial.kmn,{scope:initial.Ppn},h(initial.LcuOAuthAccountContext.Provider,{value:accountState},...panels)))))))));
}
window.addEventListener('codex-message-from-view',event=>{
 if(/^browser-sidebar-(comment-overlay-|design-overlay-)/.test(event.detail?.type))window.lcuHost.annotation(event.detail).catch(error=>console.error('Original annotation dispatch failed',error));
 if(event.detail?.type==='browser-sidebar-command')window.lcuHost.command(event.detail).catch(error=>console.error('Original browser command dispatch failed',error));
 if(event.detail?.type==='app-shell-shortcut-state-changed')window.lcuHost.shortcutState(event.detail).catch(error=>console.error('Original app-shell shortcut state failed',error));
});
function route(record) {return {conversationId:record.conversationId,browserTabId:record.browserTabId};}
function syncLayout(record){
 if(!record)return;
 requestAnimationFrame(()=>{
  if(!pages.has(record.browserTabId))return;
  const rect=panelMount.getBoundingClientRect();
  window.lcuHost.view({type:'view',...route(record),visible:record.visible,bounds:{x:rect.x,y:rect.y,width:rect.width,height:rect.height}});
 });
}
function remove(record, message) {
 if (!record) return;
 pages.delete(record.browserTabId);pending.delete(record.browserTabId);renderAnnotations();
 window.lcuHost.view({type:'destroyed',...route(record),teardownId:message.teardownId});
}
window.lcuHost.subscribe(message => {
 shared.IB.dispatchHostMessage(message);
 if(message.type==='lcu-account-updated')refreshAccount().then(renderAnnotations).catch(error=>console.error('Original account context refresh failed',error));
 if(message.type==='lcu-intl'){runtimeIntlConfig=message.runtimeIntlConfig;renderAnnotations();}
 if(message.type==='lcu-setting')for(const listener of settingsListeners.get(message.key)||[])listener(message.value);
 let record=pages.get(message.browserTabId);
 if(message.browserTabId&&!record) {
  const state=pending.get(message.browserTabId)||{};
  if(message.type==='browser-sidebar-browser-use-state')state.active=message.isActive;
  if(message.type==='browser-sidebar-state')state.snapshot=message.snapshot;
  if(message.type==='lcu-permission-prompts')state.prompts=message.prompts;
  pending.set(message.browserTabId,state);
 }
 if(message.type==='open-browser-tab') {
  if(record)return;
  record={conversationId:message.conversationId,browserTabId:message.browserTabId,cwd:message.cwd,visible:false,snapshot:pending.get(message.browserTabId)?.snapshot,prompts:pending.get(message.browserTabId)?.prompts||[]};
  pages.set(record.browserTabId,record);renderAnnotations();syncLayout(record);
 } else if(message.type==='browser-sidebar-destroy-webview'||message.type==='close-browser-tab')remove(record,message);
 else if(message.type==='toggle-browser-panel'||message.type==='browser-sidebar-open-panel-without-animation') {
  for(const page of pages.values())page.visible=message.open!==false&&page===record;
  renderAnnotations();for(const page of pages.values())syncLayout(page);
 } else if(record) {
  switch(message.type) {
   case 'lcu-permission-prompts':record.prompts=message.prompts;for(const callback of permissionSubscribers.get(record.browserTabId)||[])callback(message.prompts);break;
   case 'browser-sidebar-state':record.snapshot=message.snapshot;renderAnnotations();break;
   case 'browser-sidebar-browser-use-state':syncLayout(record);break;
  }
 }
});
new ResizeObserver(()=>{for(const record of pages.values())syncLayout(record);}).observe(panelMount);

await new Promise(resolve=>hydrateAtoms({onHydrated:resolve}));
renderAnnotations();
await oauthMounted;
await window.lcuHost.ready();
