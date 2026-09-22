// IPC transport for the unchanged original main-process fetch wrapper and
// original per-window HTTP provider (shared module export Sf).
const path = require('node:path');

module.exports = function createHttpService(generatedDirectory, options) {
 const {FetchWrapper, DeviceCheckCookieManager, IntegrityStateStore,
  generateDeviceCheckToken} = require(path.join(generatedDirectory, 'provider.cjs'));
 const {xt: desktopOriginator, St: devApiBaseUrl, Ht: prodApiBaseUrl,
  bundleIdentifier, apiUrl} = require(path.join(generatedDirectory, 'bootstrap-provider.cjs'));
 const {applicationNetwork, authClient, globalState, originalShared, buildFlavor} = options;
 for (const [name, value] of Object.entries({FetchWrapper, DeviceCheckCookieManager,
  IntegrityStateStore, generateDeviceCheckToken, desktopOriginator, devApiBaseUrl,
  prodApiBaseUrl, bundleIdentifier, apiUrl, applicationNetwork, authClient, globalState,
  originalShared, buildFlavor})) {
  if (value == null) throw Error(`Original HTTP service requires ${name}`);
 }
 if (typeof originalShared.Sf !== 'function') throw Error('Original per-window HTTP provider is unavailable');

 const fetchWrapper = new FetchWrapper(null, {
  applicationNetwork,
  desktopOriginator,
  devApiBaseUrl,
  prodApiBaseUrl,
  deviceCheckCookieManager: new DeviceCheckCookieManager({
   bundleIdentifier: bundleIdentifier(buildFlavor),
   generateToken: () => generateDeviceCheckToken({resourcesPath: process.resourcesPath}),
   url: apiUrl({
    desktopOriginator, devApiBaseUrl, prodApiBaseUrl,
   }, '/devicecheck'),
  }),
  integrityStateStore: new IntegrityStateStore(globalState),
  appServerConnectionRegistry: {
   getConnection(hostId) {
    if (hostId !== 'local') throw Error('No app-server connection for host');
    return authClient;
   },
  },
 });
 const owners = new Map();
 function ownerState(owner) {
  if (owner.isDestroyed()) throw Error('Original HTTP owner is destroyed');
  let state = owners.get(owner);
  if (state) return state;
  const provider = new originalShared.Sf((id, request, signal, progress) =>
   fetchWrapper.fetchHttp(id, request, signal, progress, undefined));
  state = {owner, provider, pending: new Set(), responses: new Map()};
  owners.set(owner, state);
  owner.once('destroyed', () => dispose(owner));
  return state;
 }
 async function fetch(owner, requestId, request, trackUploadProgress = false) {
  if (typeof requestId !== 'string' || !requestId || typeof request !== 'object' || request == null) {
   throw Error('Invalid original HTTP request');
  }
  const state = ownerState(owner);
  if (state.pending.has(requestId)) throw Error('Duplicate original HTTP request ID');
  state.pending.add(requestId);
  let result;
  try {
   const progress = trackUploadProgress ? value => {
    if (!owner.isDestroyed()) owner.send('lcu-iab:message',
     {type: 'lcu-http-progress', requestId, progress: value});
   } : undefined;
   result = await state.provider.fetch(requestId, request, progress);
   if (!('response' in result)) {
    state.pending.delete(requestId);
    return result;
   }
   const response = result.response;
   const headers = [...response.headers.entries()];
   const reader = response.body?.getReader();
   if (reader) state.responses.set(requestId, reader);
   else state.pending.delete(requestId);
   return {response: {status: response.status, statusText: response.statusText,
    headers, bodyStream: reader != null}};
  } catch (error) {
   state.pending.delete(requestId);
   throw error;
  }
 }
 async function pull(owner, requestId) {
  const state = owners.get(owner);
  if (!state || state.owner !== owner || !state.pending.has(requestId)) {
   throw Error('Original HTTP stream is unavailable for this owner');
  }
  const reader = state.responses.get(requestId);
  if (!reader) throw Error('Original HTTP response has no body stream');
  try {
   const result = await reader.read();
   if (!result.done) return {done: false, chunk: result.value};
   state.responses.delete(requestId);
   state.pending.delete(requestId);
   reader.releaseLock();
   return {done: true};
  } catch (error) {
   state.responses.delete(requestId);
   state.pending.delete(requestId);
   try {reader.releaseLock();} catch {}
   throw error;
  }
 }
 function cancel(owner, requestId) {
  const state = owners.get(owner);
  if (!state || state.owner !== owner) return;
  state.provider.cancel(requestId);
  const reader = state.responses.get(requestId);
  if (reader) {
   state.responses.delete(requestId);
   state.pending.delete(requestId);
   reader.cancel().catch(() => {});
  }
 }
 function dispose(owner, requestId) {
  const state = owners.get(owner);
  if (!state || state.owner !== owner) return;
  if (requestId != null) {cancel(owner, requestId); return;}
  owners.delete(owner);
  state.provider[Symbol.dispose]();
  for (const reader of state.responses.values()) reader.cancel().catch(() => {});
  state.responses.clear();
  state.pending.clear();
 }
 function disposeAll() {
  for (const state of [...owners.values()]) dispose(state.owner);
 }
 return {fetch, pull, cancel, dispose, disposeAll};
};
