// Forward the original Sky service unchanged and relay its original lifecycle
// hook to the signed macOS client through an LCU-owned, short-lived socket.
import {pathToFileURL} from 'node:url';
import {Buffer} from 'node:buffer';

let original;
let registered = false;
const pendingCleanup = new Map();
let cleanupInFlight;

function lifetimeSignal(runtime, session_id, turn_id) {
  const address = runtime.env.LCU_MAC_LIFETIME_SOCKET;
  if (!address || typeof runtime.nativePipe?.createConnection !== 'function') {
    throw Error('Original macOS native-pipe lifetime channel is unavailable');
  }
  return runtime.nativePipe.createConnection(address).then(socket => new Promise((resolve, reject) => {
    let data = Buffer.alloc(0);
    let finished = false;
    const timer = setTimeout(() => finish(Error('macOS native turn cleanup timed out')), 4000);
    function finish(error, result) {
      if (finished) return;
      finished = true;
      clearTimeout(timer);
      socket.end();
      if (error) reject(error); else resolve(result);
    }
    socket.on('data', chunk => {
      data = Buffer.concat([data, chunk]);
      if (data.length > 4096) return finish(Error('macOS native cleanup response is too large'));
      const newline = data.indexOf(10);
      if (newline < 0) return;
      try {
        const result = JSON.parse(data.subarray(0, newline).toString('utf8'));
        if (!result || result.notified !== true) {
          throw Error(result?.error || 'Original macOS turn-ended command failed');
        }
        finish(null, true);
      } catch (error) { finish(error); }
    });
    socket.on('error', error => finish(error));
    socket.on('close', () => finish(Error('macOS native cleanup channel closed')));
    socket.write(Buffer.from(JSON.stringify({session_id, turn_id}) + '\n'));
  }));
}

function register() {
  if (registered) return;
  const runtime = globalThis.nodeRepl;
  if (typeof runtime?.addTurnEndedHandler !== 'function') {
    throw Error('Original node_repl turn-ended hook is unavailable');
  }
  runtime.addTurnEndedHandler({timeoutMs: 4000, run: async ({session_id, turn_id}) => {
    if (typeof session_id !== 'string' || !session_id.trim() ||
        typeof turn_id !== 'string' || !turn_id.trim()) {
      throw Error('Original node_repl turn IDs are missing');
    }
    const key = JSON.stringify([session_id, turn_id]);
    pendingCleanup.set(key, {session_id, turn_id});
    await finishPendingCleanup();
  }});
  registered = true;
}

function finishPendingCleanup() {
  // The original runtime can report MCP success after a hook fails. Retain
  // native cleanup until its host acknowledges it and retry before more actions.
  if (!cleanupInFlight) {
    cleanupInFlight = (async () => {
      for (const [key, {session_id, turn_id}] of pendingCleanup) {
        await lifetimeSignal(globalThis.nodeRepl, session_id, turn_id);
        pendingCleanup.delete(key);
      }
    })().finally(() => { cleanupInFlight = undefined; });
  }
  return cleanupInFlight;
}

export async function handleRpc(request) {
  register();
  await finishPendingCleanup();
  original ??= import(pathToFileURL(globalThis.nodeRepl.env.LCU_MAC_SKY_SERVICE_PATH).href);
  return (await original).handleRpc(request);
}
