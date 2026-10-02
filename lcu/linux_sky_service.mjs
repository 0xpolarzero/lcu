// Forward the original Sky service unchanged, except for window-targeted input that the
// original Linux engine delivers with XSendEvent to toolkits that ignore it (GTK 4: keys,
// clicks, scroll, drag and pointer moves; Qt: scroll). For those windows only, the same
// action is issued through the engine's own desktop-level call (XTEST) after the engine's
// own activate_window, with window-relative coordinates converted to desktop coordinates.
// No input is implemented here. Every other request, app, and any case this wrapper cannot
// classify with confidence goes to the original service untouched.
import {pathToFileURL} from 'node:url';
import {execFile} from 'node:child_process';
import {readFile} from 'node:fs/promises';

const TOOLKIT_TTL_MS = 10_000;
const ACTIVATE_DEADLINE_MS = 1500;
const ACTIVATE_POLL_MS = 40;
const XPROP_TIMEOUT_MS = 3000;
const DEFAULT_TOOLKITS = 'gtk4,qt-scroll';
// Windows of these runtimes handle XSendEvent themselves even if they map a GTK 4 library
// (Chromium and Electron mmap icudtl.dat; Firefox is libxul).
const NOT_GTK4 = [/\/icudtl\.dat/, /\/libxul\.so/, /\/libffmpeg\.so/];

let original;
let queue = Promise.resolve();
const toolkitByPid = new Map();
const windowPid = new Map();

const KEY_METHODS = new Set(['press_key', 'key_down', 'key_up']);
const POINTER_METHODS = new Set(['click', 'scroll', 'drag', 'move']);

function enabledToolkits(env) {
  const raw = env.LCU_LINUX_INPUT_TOOLKITS ?? DEFAULT_TOOLKITS;
  return new Set(raw.split(',').map(item => item.trim()).filter(Boolean));
}

function disabled(env) {
  return ['off', '0', 'false', 'no'].includes(String(env.LCU_LINUX_INPUT_TRANSLATION ?? '').trim().toLowerCase());
}

function xprop(args) {
  return new Promise((resolve, reject) => {
    execFile('xprop', args, {timeout: XPROP_TIMEOUT_MS, env: {...process.env, LC_ALL: 'C'}, maxBuffer: 1 << 16},
      (error, stdout) => error ? reject(error) : resolve(String(stdout)));
  });
}

function cardinals(output, name) {
  const match = new RegExp(`^${name}\\([A-Z_]+\\)\\s*=\\s*(.*)$`, 'm').exec(output);
  return match ? match[1].split(',').map(item => item.trim()).filter(Boolean) : null;
}

async function windowProperties(id) {
  const output = await xprop(['-id', String(id), '_NET_WM_PID', 'WM_TRANSIENT_FOR', '_NET_WM_STATE']);
  const pid = Number(cardinals(output, '_NET_WM_PID')?.[0]);
  const parent = /^WM_TRANSIENT_FOR\(WINDOW\):\s*window id #\s*(0x[0-9a-f]+)/im.exec(output)?.[1] ?? null;
  const state = cardinals(output, '_NET_WM_STATE') ?? [];
  return {
    pid: Number.isInteger(pid) && pid > 0 ? pid : null,
    transientFor: parent ? Number.parseInt(parent, 16) : null,
    hidden: state.includes('_NET_WM_STATE_HIDDEN'),
  };
}

async function screenSize() {
  try {
    const values = cardinals(await xprop(['-root', '_NET_DESKTOP_GEOMETRY']), '_NET_DESKTOP_GEOMETRY');
    const [width, height] = (values ?? []).map(Number);
    return width > 0 && height > 0 ? {width, height} : null;
  } catch {
    return null;
  }
}

async function detectToolkit(pid) {
  const cached = toolkitByPid.get(pid);
  if (cached && Date.now() - cached.at < TOOLKIT_TTL_MS) return cached.toolkit;
  let toolkit = null;
  try {
    const maps = await readFile(`/proc/${pid}/maps`, 'utf8');
    if (/\/libgtk-4\.so/.test(maps) && !NOT_GTK4.some(pattern => pattern.test(maps))) toolkit = 'gtk4';
    else if (/\/libQt[56]Core\.so/.test(maps)) toolkit = 'qt';
  } catch {
    toolkit = null; // another account, a different PID namespace, or an exited process
  }
  toolkitByPid.set(pid, {toolkit, at: Date.now()});
  return toolkit;
}

async function classify(id) {
  const properties = await windowProperties(id);
  if (!properties.pid) return {...properties, toolkit: null};
  return {...properties, toolkit: await detectToolkit(properties.pid)};
}

function listWindows(service) {
  return service.handleRpc({type: 'execute', method: 'list_windows', args: []});
}

function finite(value) {
  return typeof value === 'number' && Number.isFinite(value);
}

function applies(toolkit, method, toolkits) {
  if (toolkit === 'gtk4') return toolkits.has('gtk4');
  if (toolkit === 'qt') return method === 'scroll' && toolkits.has('qt-scroll');
  return false;
}

function pointsOf(method, input, window) {
  if (method === 'drag') {
    return Array.isArray(input.path) && input.path.length >= 2 &&
      input.path.every(point => point && finite(point.x) && finite(point.y)) ? input.path : null;
  }
  if (method === 'click' || method === 'move') {
    return finite(input.x) && finite(input.y) && input.element_id == null ? [{x: input.x, y: input.y}] : null;
  }
  if (method === 'scroll') {
    if (input.element_id != null) return null;
    if (finite(input.x) && finite(input.y)) return [{x: input.x, y: input.y}];
    if (input.x == null && input.y == null) return [{x: Math.floor(window.width / 2), y: Math.floor(window.height / 2)}];
    return null;
  }
  return [];
}

function outsideScreen(method, input, screen) {
  if (!screen || !POINTER_METHODS.has(method)) return false;
  return (method === 'drag' ? input.path : [input]).some(point =>
    point.x < 0 || point.y < 0 || point.x >= screen.width || point.y >= screen.height);
}

function desktopInput(method, input, window, points) {
  const {window: _window, ...rest} = input;
  if (method === 'drag') {
    return {...rest, path: points.map(point => ({x: window.x + point.x, y: window.y + point.y}))};
  }
  if (POINTER_METHODS.has(method)) {
    return {...rest, x: window.x + points[0].x, y: window.y + points[0].y};
  }
  return rest;
}

async function modalChild(target, windows) {
  const dialogs = windows.filter(window => window.modal && window.id !== target.id);
  const owned = new Set([target.id]);
  const found = [];
  // A dialog may be transient for another dialog of the same window; follow the chain.
  for (let round = 0; round < 4 && found.length < dialogs.length; round++) {
    for (const dialog of dialogs) {
      if (owned.has(dialog.id)) continue;
      let properties;
      try { properties = await windowProperties(dialog.id); } catch { continue; }
      if (properties.transientFor !== null && owned.has(properties.transientFor)) {
        owned.add(dialog.id);
        found.push(dialog);
      }
    }
  }
  return found.find(window => window.focused) ?? found.at(-1) ?? null;
}

async function plan(service, request, env) {
  if (request?.type !== 'execute' || typeof request.method !== 'string' ||
      !(KEY_METHODS.has(request.method) || POINTER_METHODS.has(request.method))) return null;
  const input = Array.isArray(request.args) && request.args.length === 1 ? request.args[0] : null;
  const target = input?.window;
  if (!input || !target || !Number.isInteger(target.id)) return null;
  const method = request.method;
  if (KEY_METHODS.has(method) && typeof input.key !== 'string') return null;
  const toolkits = enabledToolkits(env);
  const classified = await classify(target.id);
  if (!applies(classified.toolkit, method, toolkits) || classified.hidden) return null;
  const windows = await listWindows(service);
  const current = Array.isArray(windows) ? windows.find(window => window.id === target.id) : null;
  if (!current) return null; // the original service reports its normal error
  const points = pointsOf(method, input, current);
  if (points === null) return null;
  // Input to a window with a modal dialog goes to that dialog, which the toolkit grabs input for.
  const focus = classified.toolkit === 'gtk4' ? await modalChild(current, windows) ?? current : current;
  const screen = await screenSize();
  // An off-screen target keeps the original behavior and the original error.
  if (outsideScreen(method, desktopInput(method, input, current, points), screen)) return null;
  return {request, method, input, points, focus, current, screen};
}

async function focused(service, id) {
  const windows = await listWindows(service);
  return Array.isArray(windows) ? windows.find(window => window.id === id) ?? null : null;
}

async function execute(service, steps) {
  let {focus, current} = steps;
  if (steps.method !== 'key_up' && !focus.focused) {
    await service.handleRpc({type: 'execute', method: 'activate_window', args: [{window: focus}]});
    const deadline = Date.now() + ACTIVATE_DEADLINE_MS;
    let seen;
    for (;;) {
      seen = await focused(service, focus.id);
      if (seen?.focused) break;
      if (Date.now() >= deadline) {
        throw Error('LCU could not give keyboard focus to the target window, so its window-targeted input was not sent. ' +
          'Try activating the window and repeating the action.');
      }
      await new Promise(resolve => setTimeout(resolve, ACTIVATE_POLL_MS));
    }
  }
  // Windows move and CSD shadows differ: convert with geometry read immediately before the call.
  const windows = await listWindows(service);
  current = Array.isArray(windows) ? windows.find(window => window.id === current.id) : null;
  if (!current) throw Error('The target window disappeared before its input could be sent.');
  const input = desktopInput(steps.method, steps.input, current, steps.points);
  if (outsideScreen(steps.method, input, steps.screen)) return service.handleRpc(steps.request);
  return service.handleRpc({type: 'execute', method: steps.method, args: [input]});
}

export async function handleRpc(request) {
  const env = globalThis.nodeRepl?.env ?? process.env;
  original ??= import(pathToFileURL(env.LCU_LINUX_SKY_SERVICE_PATH).href);
  const service = await original;
  if (disabled(env)) return service.handleRpc(request);
  let steps = null;
  try {
    steps = await plan(service, request, env);
  } catch {
    steps = null; // classification is best effort; never block the original behavior
  }
  if (!steps) return service.handleRpc(request);
  // One translated action at a time: activation, geometry and input must not interleave.
  const run = queue.then(() => execute(service, steps));
  queue = run.catch(() => {});
  return run;
}
