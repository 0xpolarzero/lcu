// Mount inside the original app scope, both query providers and _C account
// provider. pul/bul own pending state, callback claims and resume behavior.
export function createHttpFetch(host) {
 if (typeof host.httpFetch !== 'function' || typeof host.httpPull !== 'function' ||
     typeof host.httpCancel !== 'function' || typeof host.httpDispose !== 'function') {
  throw Error('Original HTTP IPC transport is unavailable');
 }
 const progressListeners = new Map();
 host.subscribe(message => {
  if (message?.type === 'lcu-http-progress') {
   progressListeners.get(message.requestId)?.(message.progress);
  }
 });
 return {
  fetch(requestId, request, onUploadProgress) {
   if (onUploadProgress) progressListeners.set(requestId, onUploadProgress);
   let disposed = false;
   const dispose = () => {
    if (disposed) return;
    disposed = true;
    progressListeners.delete(requestId);
    host.httpDispose(requestId).catch(() => {});
   };
   const task = host.httpFetch({requestId, request,
    trackUploadProgress: typeof onUploadProgress === 'function'}).then(result => {
    if (!('response' in result)) return {...result, [Symbol.dispose]: dispose};
    const {status, statusText, headers, bodyStream} = result.response;
    const body = bodyStream ? new ReadableStream({
     async pull(controller) {
      try {
       const value = await host.httpPull(requestId);
       if (value.done) controller.close();
       else controller.enqueue(new Uint8Array(value.chunk));
      } catch (error) {controller.error(error);}
     },
     cancel() {return host.httpCancel(requestId);},
    }) : null;
    return {
     response: new Response(body, {status, statusText, headers}),
     [Symbol.dispose]: dispose,
    };
   }).finally(() => progressListeners.delete(requestId));
   task[Symbol.dispose] = dispose;
   return task;
  },
  cancel(requestId) {return host.httpCancel(requestId);},
 };
}

export function createOAuthOperations(initial, channel) {
 const React = initial.lcuOAuthReact;
 if (!React || typeof channel.subscribe !== 'function') {
  throw Error('Original OAuth hooks require a trusted host channel');
 }
 function Operations() {
  const pending = initial.lcuUseAppConnectOAuthPending();
  const finish = initial.lcuUseAppConnectOAuthCallback();
  const latest = React.useRef({pending, finish});
  latest.current = {pending, finish};
  React.useEffect(() => {
   const unsubscribe = channel.subscribe(async request => {
   if (request?.type !== 'connector-oauth-callback' && request?.type !== 'lcu-oauth-operation') return;
   const {pending, finish} = latest.current;
   try {
    let result;
    if (request.type === 'connector-oauth-callback' || request.operation === 'callback') {
     // Original bul claims the callback itself. The host cannot assert a claim.
     result = await finish({fullRedirectUrl: request.fullRedirectUrl ?? request.params?.fullRedirectUrl,
      callbackReceivedAtMs: performance.timeOrigin + performance.now()});
    } else if (request.operation === 'register') result = pending.markAppConnectOAuthPending(request.params);
    else if (request.operation === 'clear') result = pending.clearPendingAppConnect(request.params);
    else throw Error('Unknown original OAuth bridge operation');
    if (request.requestId != null) await channel.reply({requestId: request.requestId, result});
   } catch {
    // Callback URLs may contain credentials. Never log the request or error.
    if (request.requestId != null) await channel.reply({requestId: request.requestId, error: 'Original OAuth operation failed'});
   }
   });
   channel.onReady?.();
   return typeof unsubscribe === 'function' ? unsubscribe : undefined;
  }, []);
  return null;
 }
 return Operations;
}

export function createOAuthBridge(initial, channel) {
 const Operations = createOAuthOperations(initial, channel);
 return function OAuthBridge({account}) {
  return initial.lcuOAuthReact.createElement(initial.LcuOAuthAccountContext.Provider,
   {value: account}, initial.lcuOAuthReact.createElement(Operations));
 };
}
