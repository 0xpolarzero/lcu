#!/usr/bin/env node
// Build-time extraction only. Full original app.asar remains bundled unchanged.
// Run with Node --expose-internals; the parser is Node's bundled Acorn, not a network dependency.
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const acorn = require('internal/deps/acorn/acorn/dist/acorn');
const [application, outputDirectory] = process.argv.slice(2);
if (!application || !outputDirectory) throw Error('Usage: node --expose-internals extract_iab_host.cjs APPLICATION OUTPUT');
const archive = fs.readFileSync(path.join(application, 'resources/app.asar'));
const tree = JSON.parse(archive.subarray(16, 16 + archive.readUInt32LE(12)).toString());
const base = 8 + archive.readUInt32LE(4);
function sha256(value) { return crypto.createHash('sha256').update(value).digest('hex'); }
function readOriginal(name, expected) {
 let item = tree;
 for (const component of ('.vite/build/' + name).split('/')) item = item.files[component];
 if (item.unpacked || item.offset == null) throw Error('Expected packed original module: ' + name);
 const bytes = archive.subarray(base + Number(item.offset), base + Number(item.offset) + item.size);
 if (sha256(bytes) !== expected) throw Error('Pinned original IAB module changed: ' + name);
 return bytes.toString('utf8');
}
const sources = {
 auth: {name:'src-C3YaUE83.js',sha256:'14c8c23e8b8dfa874d3fb5a50d54fb28eccf55fb83232c3ab29cb7c0ef0a0472'},
 main: {name: 'main-DUHZj4_w.js', sha256: '9e8a3bd79c817064f28693ca26aa1378895e07ab2108c78c42d0ea20dac9d66e'},
 bootstrap: {name: 'bootstrap-DF0QwAxC.js', sha256: '5787d416ccbd7be549251d2c691f9c2579d6960f3ccd470037d97486c93fdf0f'},
};
function freeNames(node){
 const free=new Set(); const members=new Set();
 function names(pattern,set){if(!pattern)return; switch(pattern.type){case'Identifier':set.add(pattern.name);break;case'RestElement':names(pattern.argument,set);break;case'AssignmentPattern':names(pattern.left,set);break;case'ArrayPattern':pattern.elements.forEach(p=>names(p,set));break;case'ObjectPattern':pattern.properties.forEach(p=>names(p.type==='RestElement'?p.argument:p.value,set));}}
 function vars(n,set){if(!n||typeof n!=='object')return;if(['FunctionDeclaration','FunctionExpression','ArrowFunctionExpression','ClassDeclaration','ClassExpression'].includes(n.type))return;if(n.type==='VariableDeclaration'&&n.kind==='var')n.declarations.forEach(d=>names(d.id,set));for(const [key,value]of Object.entries(n)){if(['start','end','loc'].includes(key))continue;if(Array.isArray(value))value.forEach(c=>vars(c,set));else if(value&&typeof value==='object')vars(value,set);}}
 function walk(n,scopes){if(!n||typeof n!=='object')return;
  if(n.type==='MetaProperty')return;
  if(n.type==='Identifier'){if(!scopes.some(s=>s.has(n.name)))free.add(n.name);return;}
  if(['FunctionDeclaration','FunctionExpression','ArrowFunctionExpression'].includes(n.type)){
   const local=new Set();names(n.id,local);n.params.forEach(p=>names(p,local));vars(n.body,local);const child=[local,...scopes];
   function defaults(p){if(!p)return;if(p.type==='AssignmentPattern'){walk(p.right,child);defaults(p.left);}else if(p.type==='ObjectPattern')p.properties.forEach(x=>defaults(x.value??x.argument));else if(p.type==='ArrayPattern')p.elements.forEach(defaults);else if(p.type==='RestElement')defaults(p.argument);}n.params.forEach(defaults);walk(n.body,child);return;
  }
  if(n.type==='BlockStatement'||n.type==='Program'){
   const local=new Set();for(const child of n.body){if(child.type==='VariableDeclaration')child.declarations.forEach(d=>names(d.id,local));if(child.type==='FunctionDeclaration'||child.type==='ClassDeclaration')names(child.id,local);}
   n.body.forEach(child=>walk(child,[local,...scopes]));return;
  }
  if(n.type==='VariableDeclarator'){walk(n.init,scopes);function patternDefaults(p){if(!p)return;if(p.type==='AssignmentPattern'){walk(p.right,scopes);patternDefaults(p.left);}else if(p.type==='ObjectPattern')p.properties.forEach(x=>{if(x.computed)walk(x.key,scopes);patternDefaults(x.value??x.argument)});else if(p.type==='ArrayPattern')p.elements.forEach(patternDefaults);else if(p.type==='RestElement')patternDefaults(p.argument);}patternDefaults(n.id);return;}
  if(n.type==='MemberExpression'){if(n.object.type==='Identifier'&&!scopes.some(s=>s.has(n.object.name)))members.add(n.object.name+'.'+(n.property.name??n.property.value));walk(n.object,scopes);if(n.computed)walk(n.property,scopes);return;}
  if(n.type==='Property'||n.type==='MethodDefinition'||n.type==='PropertyDefinition'){if(n.computed)walk(n.key,scopes);walk(n.value,scopes);return;}
  if(n.type==='ClassDeclaration'||n.type==='ClassExpression'){const local=new Set();names(n.id,local);walk(n.superClass,scopes);walk(n.body,[local,...scopes]);return;}
  if(n.type==='CatchClause'){const local=new Set();names(n.param,local);walk(n.body,[local,...scopes]);return;}
  if(n.type==='LabeledStatement'){walk(n.body,scopes);return;}
  if(n.type==='BreakStatement'||n.type==='ContinueStatement')return;
  if(n.type==='ForStatement'||n.type==='ForInStatement'||n.type==='ForOfStatement'){
   const local=new Set();const decl=n.init??n.left;if(decl?.type==='VariableDeclaration')decl.declarations.forEach(d=>names(d.id,local));
   for(const [key,value] of Object.entries(n)){if(['start','end','type'].includes(key))continue;if(Array.isArray(value))value.forEach(c=>walk(c,[local,...scopes]));else if(value&&typeof value==='object')walk(value,[local,...scopes]);}return;
  }
  for(const [key,value]of Object.entries(n)){if(['start','end','loc'].includes(key))continue;if(Array.isArray(value))value.forEach(c=>walk(c,scopes));else if(value&&typeof value==='object')walk(value,scopes);}
 }
 walk(node,[]);free.members=members;return free;
}

function extract(source, headerEnd, roots) {
 const code = readOriginal(source.name, source.sha256);
 const ast = acorn.parse(code, {ecmaVersion: 'latest', sourceType: 'script'});
 const declarations = new Map();
 for (const statement of ast.body) {
  if (statement.type === 'VariableDeclaration') for (const d of statement.declarations) {
   if (d.id.type === 'Identifier') declarations.set(d.id.name, {node:d, name:d.id.name, text:`${statement.kind} ${code.slice(d.start,d.end)};`, start:d.start});
  }
  if (['FunctionDeclaration','ClassDeclaration'].includes(statement.type)) declarations.set(statement.id.name, {node:statement,name:statement.id.name,text:code.slice(statement.start,statement.end),start:statement.start});
 }
 const selected = new Set(), initializers = new Set(), unresolved = new Set();
 function add(name) {
  if (selected.has(name)) return;
  const d = declarations.get(name);
  if (!d) { unresolved.add(name); return; }
  if (d.start < headerEnd) return;
  selected.add(name);
  for (const name of freeNames(d.node)) add(name);
 }
 for (const name of Object.values(roots)) add(name);
 // Preserve original top-level declaration initialization, especially enum IIFEs.
 for (let changed = true; changed;) {
  changed = false;
  for (const statement of ast.body) {
   if (statement.start < headerEnd || statement.type !== 'ExpressionStatement' || initializers.has(statement)) continue;
   const names = freeNames(statement);
   if (names.has('exports') || ![...names].some(name => selected.has(name))) continue;
   initializers.add(statement); changed = true;
   for (const name of names) add(name);
  }
 }
 const body = [...[...selected].map(name => declarations.get(name)), ...[...initializers].map(node => ({node, name:'initializer',text:code.slice(node.start,node.end),start:node.start}))].sort((a,b)=>a.start-b.start);
 const ledger = body.map(d => ({name:d.name, startByte:Buffer.byteLength(code.slice(0,d.node.start)), endByte:Buffer.byteLength(code.slice(0,d.node.end)), sha256:sha256(code.slice(d.node.start,d.node.end))}));
 const prefix = `const lcuGeneratedDirectory=__dirname;\n__dirname=require('node:path').join(process.env.LCU_APPLICATION_PATH,'resources/app.asar/.vite/build');\nrequire=require('node:module').createRequire(require('node:path').join(__dirname,${JSON.stringify(source.name)}));\n`;
 let header = code.slice(0,headerEnd);
 const originalImport = 'a=require("./bootstrap-DF0QwAxC.js")';
 const replacement = 'a=require(require("node:path").join(lcuGeneratedDirectory,"bootstrap-provider.cjs"))';
 if (source === sources.main) {
  if (!header.includes(originalImport)) throw Error('Original bootstrap import is missing');
  header = header.replace(originalImport,replacement);
 }
 const initializeOriginal = source === sources.auth ? '\nrequire("./src-C3YaUE83.js");\n' : '\n';
 const output = prefix + header + initializeOriginal + body.map(d=>d.text).join('\n') + '\nmodule.exports={' + Object.entries(roots).map(([name,local])=>JSON.stringify(name)+':'+local).join(',') + '};\n';
 return {output, ledger, unresolved:[...unresolved], members:[...new Set(body.flatMap(d=>[...freeNames(d.node).members]))]};
}
const mainExports = {IabProvider:'fYe',createIabServer:'NYe',BrowserSessionRegistry:'uX',BrowserHost:'zZe',createCommentModePolicy:'LBe',createSiteBootstrap:'HXe',FeatureOverridesSchema:'Nte',getFeatures:'Cr',normalizeFeatures:'Or',updateFeatures:'Dr',RuntimeMessageSchema:'GWe',isBrowserPageEvent:'lte',siteToolsEvent:'SZ',siteAnnotationsEvent:'bZ',parseRendererPopupFrame:'ke',popupWindowSurfaceOptions:'z9',popupWindowColors:'L9',DesktopSettingsService:'lBe',isPrimaryWindowPersistedAtom:'oQ',mergePersistedAtom:'ABe',FetchWrapper:'wEe',DeviceCheckCookieManager:'Ije',IntegrityStateStore:'pEe',generateDeviceCheckToken:'or',resolveBrowserNavigation:'AZ',readAccountInfo:'pT'};
const bootstrapExports = {Et:'Ew',_:'UO',dn:'Ge',en:'j',g:'VO',gn:'re',h:'HO',nn:'kt',v:'lk',ApplicationNetwork:'Pt',DesktopSettingsStore:'vD',createGlobalState:'OD',mt:'aT',xt:'Jw',St:'qw',Ht:'Kw',Xt:'tC',createDeepLinkQueue:'dk',ht:'uT',_t:'rT',$t:'Ut',ut:'cT',B:'NE',ft:'lT',dt:'oT',pt:'sT',bundleIdentifier:'Ut',apiUrl:'rT'};
const main = extract(sources.main,1477,mainExports);
// The app-wide dispatcher also handles unrelated app UI. Keep every case allowed
// by its original browser runtime schema, with each case body byte-identical.
const mainCode=readOriginal(sources.main.name,sources.main.sha256);
const mainAst=acorn.parse(mainCode,{ecmaVersion:'latest'});
const originalMenu=mainAst.body.find(node=>node.type==='FunctionDeclaration'&&node.id.name==='Frt');
const originalFindAccelerators=originalMenu?.body.body[0]?.declarations?.find(node=>node.id.name==='C')?.init;
if(originalFindAccelerators?.type!=='ConditionalExpression'||originalFindAccelerators.consequent?.elements?.length!==3||originalFindAccelerators.alternate?.elements?.length!==3)throw Error('Original browser Find menu accelerators changed');
main.output+='\nmodule.exports.browserFindMenuAccelerators=function(r){return '+mainCode.slice(originalFindAccelerators.start,originalFindAccelerators.end)+'};\n';
const copilotServiceSource='"is-copilot-api-available":async()=>({available:!1})';
if(mainCode.split(copilotServiceSource).length!==2)throw Error('Original Linux Copilot availability service changed');
main.output+='\nmodule.exports.isCopilotApiAvailable='+copilotServiceSource.slice(copilotServiceSource.indexOf(':')+1)+';\n';
const runtimeCases=[], annotationCases=[], commandCases=[];
const persistedMembers=[];
const persistedNames=new Set(['sendPersistedAtomState','updatePersistedAtomState','broadcastPersistedAtomUpdate','deletePersistedAtomStateKeys','resetPersistedAtomState']);
function findRuntimeDispatcher(node) {
 if (!node || typeof node!=='object') return;
 if(node.type==='MethodDefinition'&&persistedNames.has(node.key.name))persistedMembers.push(node);
 if(node.type==='MethodDefinition'&&node.key.name==='handleMessage') {
  for(const statement of node.value.body.body) if(statement.type==='SwitchStatement') {
   const cases=statement.cases.filter(item=>item.test?.type==='TemplateLiteral'&&item.test.quasis[0]?.value.cooked.startsWith('browser-sidebar-runtime-'));
   if(cases.some(item=>item.test.quasis[0].value.cooked==='browser-sidebar-runtime-open-comment-preview')){runtimeCases.push(...cases);annotationCases.push(...statement.cases.filter(item=>item.test?.type==='TemplateLiteral'&&/^browser-sidebar-(comment-overlay-|design-overlay-)/.test(item.test.quasis[0]?.value.cooked)));commandCases.push(...statement.cases.filter(item=>item.test?.type==='TemplateLiteral'&&item.test.quasis[0]?.value.cooked==='browser-sidebar-command'));}
  }
 }
 for(const [key,value] of Object.entries(node)) if(!['start','end'].includes(key)) {
  if(Array.isArray(value))value.forEach(findRuntimeDispatcher);else if(value&&typeof value==='object')findRuntimeDispatcher(value);
 }
}
findRuntimeDispatcher(mainAst);
if(persistedMembers.length!==persistedNames.size)throw Error('Original persisted-atom method inventory changed');
main.output+='\nmodule.exports.PersistedAtomHost=class{'+persistedMembers.map(node=>mainCode.slice(node.start,node.end)).join('')+'};\n';
const schemaNode=mainAst.body.filter(node=>node.type==='VariableDeclaration').flatMap(node=>node.declarations).find(node=>node.id.name==='GWe');
const schemaTypes=new Set(mainCode.slice(schemaNode.start,schemaNode.end).match(/browser-sidebar-runtime-[a-z-]+/g));
const caseTypes=new Set(runtimeCases.map(node=>node.test.quasis[0].value.cooked));
if(runtimeCases.length!==17 || schemaTypes.size!==caseTypes.size || [...schemaTypes].some(type=>!caseTypes.has(type)))throw Error('Original browser runtime dispatcher/schema inventory changed');
const runtimeDispatcher='async function(e,t){switch(t.type){'+runtimeCases.map(node=>mainCode.slice(node.start,node.end)).join('')+'}}';
const dispatcherNames=freeNames(acorn.parse('('+runtimeDispatcher+')',{ecmaVersion:'latest'}).body[0].expression);
if([...dispatcherNames].some(name=>name!=='a'))throw Error('Original browser runtime dispatcher acquired unretained dependencies');
main.output+='\nmodule.exports.dispatchBrowserRuntimeMessage='+runtimeDispatcher+';\n';
if(annotationCases.length!==14)throw Error('Original annotation dispatcher inventory changed');
main.output+='\nmodule.exports.dispatchAnnotationMessage=async function(e,t){switch(t.type){'+annotationCases.map(node=>mainCode.slice(node.start,node.end)).join('')+'}};\n';
if(commandCases.length!==1)throw Error('Original browser command dispatcher inventory changed');
main.output+='\nmodule.exports.dispatchBrowserCommand=async function(e,t){switch(t.type){'+mainCode.slice(commandCases[0].start,commandCases[0].end)+'}};\n';
const annotationCaseLedger=annotationCases.map(node=>({type:node.test.quasis[0].value.cooked,startByte:Buffer.byteLength(mainCode.slice(0,node.start)),endByte:Buffer.byteLength(mainCode.slice(0,node.end)),sha256:sha256(mainCode.slice(node.start,node.end))}));
const runtimeCaseLedger=runtimeCases.map(node=>({type:node.test.quasis[0].value.cooked,startByte:Buffer.byteLength(mainCode.slice(0,node.start)),endByte:Buffer.byteLength(mainCode.slice(0,node.end)),sha256:sha256(mainCode.slice(node.start,node.end))}));
const bootstrapCode = readOriginal(sources.bootstrap.name,sources.bootstrap.sha256);
const bootstrap = extract(sources.bootstrap,bootstrapCode.indexOf('function te('),bootstrapExports);
const missingBootstrapMembers=main.members.filter(m=>m.startsWith('a.')&&!(m.slice(2) in bootstrapExports));
if(missingBootstrapMembers.length)throw Error('Unretained original bootstrap exports: '+missingBootstrapMembers.join(', '));
const authCode=readOriginal(sources.auth.name,sources.auth.sha256);
const authAst=acorn.parse(authCode,{ecmaVersion:'latest'});
const appServerClass=authAst.body.filter(node=>node.type==='VariableDeclaration').flatMap(node=>node.declarations).find(node=>node.id.name==='D$').init;
const authMemberNames=new Set(['authTokenGeneration','authTokenCache','authTokenPromise','eagerAuthTokenRefreshPromise','forcedAuthTokenRefreshPromise','backendAuth','getAuthToken','getCachedAuthToken','getBackendRequestAuth','getAuthenticatedPrincipal','getCachedAuthenticatedPrincipal','getAuthMethod','getAccount','fetchAuthToken','refreshCachedAuthToken','fetchForcedAuthToken','refreshCachedAuthTokenAsync','logAuthStatusResult','requestAuthStatus','clearAuthTokenCache','setAuthTokenCache','publishAuthenticatedPrincipalChange','getAuthStatusTimeoutMs','logger','catalogRequests','catalogRequestGeneration','authenticatedPrincipalChangeHandlers','userVerification','isLocal']);
const authMembers=appServerClass.body.body.filter(member=>authMemberNames.has(member.key.name));
if(authMembers.length!==authMemberNames.size)throw Error('Original auth-cache member inventory changed');
const authClass='class AuthTokenCache{'+authMembers.map(member=>authCode.slice(member.start,member.end)).join('')+'}';
const authClassAst=acorn.parse(authClass,{ecmaVersion:'latest'}).body[0];
const authRoots={BackendAuth:'HB'};
for(const name of freeNames(authClassAst))if(!['Map','Set'].includes(name))authRoots[name]=name;
const auth=extract(sources.auth,authCode.indexOf('var T='),authRoots);
auth.output+='\n'+authClass+'\nmodule.exports.AuthTokenCache=AuthTokenCache;\n';
const authMemberLedger=authMembers.map(member=>({name:member.key.name,startByte:Buffer.byteLength(authCode.slice(0,member.start)),endByte:Buffer.byteLength(authCode.slice(0,member.end)),sha256:sha256(authCode.slice(member.start,member.end))}));
fs.mkdirSync(outputDirectory,{recursive:true});
const rendererDerivations=[];
function rendererModule(name,suffix) {
 let item=tree;for(const part of ('webview/assets/'+name).split('/'))item=item.files[part];
 const bytes=archive.subarray(base+Number(item.offset),base+Number(item.offset)+item.size),code=bytes.toString('utf8');
 acorn.parse(code,{ecmaVersion:'latest',sourceType:'module'});
 const output=code+'\n'+suffix+'\n';
 acorn.parse(output,{ecmaVersion:'latest',sourceType:'module'});
 fs.writeFileSync(path.join(outputDirectory,'renderer',name),output);
 rendererDerivations.push({path:'webview/assets/'+name,originalSha256:sha256(bytes),outputSha256:sha256(output),adaptation:'Original module bytes unchanged; append standalone exports/initializer.',appendedSource:suffix});
}
fs.mkdirSync(path.join(outputDirectory,'renderer'),{recursive:true});
rendererModule('tab-content-b70d652be669.js','cl(); export {Wc as LcuAnnotationOverlay}; export {lm as LcuBrowserPanel};');
rendererModule('app-initial-430deae5a13a.js','Fvt(); ogt(); nb(); Q(); export {Mvt as LcuQueryScopeProvider, Xwl as lcuCreateQueryClient, Xxt as LcuReactQueryProvider}; export function lcuSetServices(services){ZH=services;} Uul(); yHn(); qbl(); yPa(); sea(); export {Hbl as lcuInitializePersistedAtoms}; export {Zx as LcuThreadScope, fS as LcuRouteScope, tPa as LcuAppShellLayout, sbt as LcuMemoryRouter, iea as LcuResizeObserverProvider}; export {pHn as lcuEmptyAccountState, hHn as lcuMapAccountState, pul as lcuUseAppConnectOAuthPending, bul as lcuUseAppConnectOAuthCallback, _C as LcuOAuthAccountContext, Pul as lcuOAuthReact};');
rendererModule('app-primary-1ee15bca6237.js','n0(); export {THe as LcuFindBar};');

for (const [filename,result] of [['provider.cjs',main],['bootstrap-provider.cjs',bootstrap],['auth-provider.cjs',auth]]) {
 acorn.parse(result.output,{ecmaVersion:'latest'});
 fs.writeFileSync(path.join(outputDirectory,filename),result.output);
}
fs.writeFileSync(path.join(outputDirectory,'derivation.json'),JSON.stringify({
 sourcePackageVersion:'26.915.31945',
 adaptations:[
  'Only selected original top-level declarations and their initializers are executed; the unchanged full app.asar is retained alongside them.',
  'Original relative module resolution and __dirname point into the bundled app.asar.',
  'The original main bootstrap import points to extracted original bootstrap declarations, avoiding automatic launch of the full Codex desktop app.',
  'Original declarations are exported under descriptive names for the standalone host adapter.',
  'The original shared src module is initialized before its extracted auth declarations, preserving its global Zod and Symbol setup.',
  'Original auth-cache fields/methods are retained unchanged in a derived class with a standalone transport adapter; account routing and abort behavior remain original HB code.',
  'Original getAuthMethod/getAccount, account-info JWT metadata producer, and Linux Copilot availability service are retained unchanged for account context.',
  'Original Frt browser Find menu accelerator expression is copied unchanged for the standalone native menu adapter.',
  'All 17 browser runtime IPC switch cases are copied unchanged from the original app dispatcher, behind its unchanged browser-only message schema; the unrelated avatar/app message preamble cannot match that schema.'
 ],
 browserRuntimeDispatchCases:runtimeCaseLedger,
 annotationDispatchCases:annotationCaseLedger,
 browserCommandCase:{startByte:Buffer.byteLength(mainCode.slice(0,commandCases[0].start)),endByte:Buffer.byteLength(mainCode.slice(0,commandCases[0].end)),sha256:sha256(mainCode.slice(commandCases[0].start,commandCases[0].end))},
 browserFindMenuAccelerators:{startByte:Buffer.byteLength(mainCode.slice(0,originalFindAccelerators.start)),endByte:Buffer.byteLength(mainCode.slice(0,originalFindAccelerators.end)),sha256:sha256(mainCode.slice(originalFindAccelerators.start,originalFindAccelerators.end))},
 rendererDerivations,
 persistedAtomMethods:persistedMembers.map(node=>({name:node.key.name,startByte:Buffer.byteLength(mainCode.slice(0,node.start)),endByte:Buffer.byteLength(mainCode.slice(0,node.end)),sha256:sha256(mainCode.slice(node.start,node.end))})),
 authCacheMembers:authMemberLedger,
 copilotAvailabilityService:{startByte:Buffer.byteLength(mainCode.slice(0,mainCode.indexOf(copilotServiceSource))),endByte:Buffer.byteLength(mainCode.slice(0,mainCode.indexOf(copilotServiceSource)+copilotServiceSource.length)),sha256:sha256(copilotServiceSource)},
 modules:[{...sources.auth,output:'auth-provider.cjs',outputSha256:sha256(auth.output),declarations:auth.ledger,unresolved:auth.unresolved},{...sources.main,output:'provider.cjs',outputSha256:sha256(main.output),declarations:main.ledger,unresolved:main.unresolved},{...sources.bootstrap,output:'bootstrap-provider.cjs',outputSha256:sha256(bootstrap.output),declarations:bootstrap.ledger,unresolved:bootstrap.unresolved}]
},null,2)+'\n');
console.log(JSON.stringify({outputDirectory,mainDeclarations:main.ledger.length,bootstrapDeclarations:bootstrap.ledger.length}));
