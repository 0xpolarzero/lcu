// Forward the original Sky service unchanged, except for window-targeted input that the
// original Linux engine delivers with XSendEvent to toolkits that ignore it (GTK 4: keys,
// clicks, scroll, drag and pointer moves; Qt: scroll). For those windows only, the same
// action is issued through the engine's own desktop-level call (XTEST) after the engine's
// own activate_window, with window-relative coordinates converted to desktop coordinates.
// No input is implemented here. Every other request, app, and any case this wrapper cannot
// classify with confidence goes to the original service untouched. A translated request is
// planned, focused, verified and sent inside one serialized queue; if the target cannot be
// focused, the point is outside the target, or the target owns a modal dialog and the input is
// a pointer action, the call fails with an explicit error and nothing is sent anywhere.
import {pathToFileURL} from 'node:url';
import {execFile} from 'node:child_process';
import {readFile, readlink} from 'node:fs/promises';
import {hostname} from 'node:os';

const TOOLKIT_TTL_MS = 10_000;
const ACTIVATE_DEADLINE_MS = 1500;
const ACTIVATE_POLL_MS = 40;
const XPROP_TIMEOUT_MS = 3000;
const DEFAULT_TOOLKITS = 'gtk4,qt-scroll';
// Windows of these runtimes handle XSendEvent themselves even if they map a GTK 4 library
// (Chromium and Electron mmap icudtl.dat; Firefox is libxul).
const NOT_GTK4 = [/\/icudtl\.dat/, /\/libxul\.so/, /\/libffmpeg\.so/];

// Replaceable by tests only.
export const deps = {
  readFile: path => readFile(path, 'utf8'),
  readLink: path => readlink(path),
  hostname: () => hostname(),
  sleep: ms => new Promise(resolve => setTimeout(resolve, ms)),
  xprop: args => new Promise((resolve, reject) => {
    execFile('xprop', args, {timeout: XPROP_TIMEOUT_MS, env: {...process.env, LC_ALL: 'C'}, maxBuffer: 1 << 16},
      (error, stdout) => error ? reject(error) : resolve(String(stdout)));
  }),
};

let original;
let queue = Promise.resolve();
const toolkitByPid = new Map();
// Translated key holds: the desktop key stays down while any (target, chord) owner holds it.
let holds = [];
const heldTokens = new Map();
const PASS = Symbol('pass');

const KEY_METHODS = new Set(['press_key', 'key_down', 'key_up']);
const POINTER_METHODS = new Set(['click', 'scroll', 'drag', 'move']);

class Rejection extends Error {}

export function resetForTests() {
  original = undefined;
  queue = Promise.resolve();
  toolkitByPid.clear();
  holds = [];
  heldTokens.clear();
}

function enabledToolkits(env) {
  const raw = env.LCU_LINUX_INPUT_TOOLKITS ?? DEFAULT_TOOLKITS;
  return new Set(raw.split(',').map(item => item.trim()).filter(Boolean));
}

function disabled(env) {
  return ['off', '0', 'false', 'no'].includes(String(env.LCU_LINUX_INPUT_TRANSLATION ?? '').trim().toLowerCase());
}

function xprop(args) {
  return deps.xprop(args);
}

function cardinals(output, name) {
  const match = new RegExp(`^${name}\\([A-Z_]+\\)\\s*=\\s*(.*)$`, 'm').exec(output);
  return match ? match[1].split(',').map(item => item.trim()).filter(Boolean) : null;
}

function sameHost(machine) {
  if (typeof machine !== 'string' || !machine) return false;
  const normalize = name => String(name).trim().toLowerCase().replace(/\.$/, '');
  return normalize(machine) === normalize(deps.hostname());
}

async function windowProperties(id) {
  const output = await xprop(['-id', String(id), '_NET_WM_PID', 'WM_CLIENT_MACHINE', 'WM_TRANSIENT_FOR', '_NET_WM_STATE']);
  const pid = Number(cardinals(output, '_NET_WM_PID')?.[0]);
  const parent = /^WM_TRANSIENT_FOR\(WINDOW\):\s*window id #\s*(0x[0-9a-f]+)/im.exec(output)?.[1] ?? null;
  const state = cardinals(output, '_NET_WM_STATE') ?? [];
  const machine = /^WM_CLIENT_MACHINE\([A-Z_]+\)\s*=\s*"(.*)"\s*$/m.exec(output)?.[1] ?? null;
  return {
    pid: Number.isInteger(pid) && pid > 0 ? pid : null,
    machine,
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

// Field 22 of /proc/<pid>/stat (process start time in clock ticks); the command name may contain
// spaces and parentheses, so fields are counted after the last closing parenthesis.
async function processStart(pid) {
  try {
    const stat = await deps.readFile(`/proc/${pid}/stat`);
    const fields = stat.slice(stat.lastIndexOf(')') + 1).trim().split(/\s+/);
    return /^\d+$/.test(fields[19] ?? '') ? fields[19] : null;
  } catch {
    return null;
  }
}

// _NET_WM_PID is the client's PID on the client's machine (EWMH). It identifies a local process only
// when this process shares the PID namespace, so a window from another namespace is never classified.
async function sharesPidNamespace(pid) {
  let theirs;
  try { theirs = await deps.readLink(`/proc/${pid}/ns/pid`); } catch { return false; }
  try { return theirs === await deps.readLink('/proc/self/ns/pid'); } catch { return true; }
}

async function detectToolkit(pid) {
  const start = await processStart(pid);
  if (!start) return null; // an exited process, another account or another PID namespace
  const cached = toolkitByPid.get(pid);
  if (cached && cached.start === start && Date.now() - cached.at < TOOLKIT_TTL_MS) return cached.toolkit;
  toolkitByPid.delete(pid);
  if (!await sharesPidNamespace(pid)) return null;
  let toolkit = null;
  try {
    const maps = await deps.readFile(`/proc/${pid}/maps`);
    if (/\/libgtk-4\.so/.test(maps) && !NOT_GTK4.some(pattern => pattern.test(maps))) toolkit = 'gtk4';
    else if (/\/libQt[56]Core\.so/.test(maps)) toolkit = 'qt';
  } catch {
    return null;
  }
  if (await processStart(pid) !== start) return null; // the id was reused while it was being read
  toolkitByPid.set(pid, {toolkit, start, at: Date.now()});
  return toolkit;
}

async function classify(id) {
  const properties = await windowProperties(id);
  if (!properties.pid || !sameHost(properties.machine)) return {...properties, toolkit: null};
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

// The first point of a pointer action (the only point of a click, scroll or move, the start of a
// drag) must lie in the target's client rectangle as it is now; a stale point would otherwise land
// on whatever application is at that place on the desktop. Drag end points may leave the target.
function requireInside(method, points, window) {
  if (!POINTER_METHODS.has(method)) return;
  const point = points[0];
  if (point.x >= 0 && point.y >= 0 && point.x < window.width && point.y < window.height) return;
  throw new Rejection(`The point (${point.x}, ${point.y}) is outside the target window's current bounds ` +
    `(${window.width}x${window.height} at ${window.x},${window.y}), so no input was sent. The window may have moved or ` +
    'been resized; read its current state and repeat the action with coordinates inside it.');
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

function chordTokens(key) {
  const tokens = key.trim().toLowerCase() === '+' ? ['+'] : key.toLowerCase().split('+').map(item => item.trim()).filter(Boolean);
  return tokens.length ? tokens : null;
}

function takeHold(targetId, tokens) {
  const chord = tokens.join('+');
  const index = holds.findIndex(hold => hold.targetId === targetId && hold.chord === chord);
  if (index < 0) return null;
  holds.splice(index, 1);
  return chord;
}

function addOwners(tokens) {
  const fresh = [];
  for (const token of tokens) {
    const count = heldTokens.get(token) ?? 0;
    if (count === 0) fresh.push(token);
    heldTokens.set(token, count + 1);
  }
  return fresh;
}

function dropOwners(tokens) {
  const released = [];
  for (const token of tokens) {
    const count = (heldTokens.get(token) ?? 1) - 1;
    if (count <= 0) { heldTokens.delete(token); released.push(token); } else heldTokens.set(token, count);
  }
  return released;
}

function keyForTokens(subset, tokens, original) {
  return subset.length === tokens.length ? original : subset.join('+');
}

async function waitForFocus(service, id) {
  const deadline = Date.now() + ACTIVATE_DEADLINE_MS;
  for (;;) {
    const windows = await listWindows(service);
    if ((Array.isArray(windows) ? windows.find(window => window.id === id) : null)?.focused) return;
    if (Date.now() >= deadline) {
      throw new Rejection('LCU could not give keyboard focus to the target window, so its window-targeted input was not sent. ' +
        'Try activating the window and repeating the action.');
    }
    await deps.sleep(ACTIVATE_POLL_MS);
  }
}

// Everything happens inside the serialized queue: the window list, the modal state and the focus are
// read for this request only after every earlier translated request has finished.
async function translate(service, request, env) {
  const {method} = request;
  const input = request.args[0];
  const target = input.window;
  const keyboard = KEY_METHODS.has(method);

  if (method === 'key_up') {
    // Release a translated hold at the desktop level, whatever happened to its window since.
    const tokens = chordTokens(input.key);
    const chord = tokens && takeHold(target.id, tokens);
    if (!chord) return PASS;
    const released = dropOwners(tokens);
    if (!released.length) return null; // another owner still holds these keys
    const {window: _window, ...rest} = input;
    return service.handleRpc({type: 'execute', method, args: [{...rest, key: keyForTokens(released, tokens, input.key)}]});
  }

  let plan;
  try {
    const classified = await classify(target.id);
    if (!applies(classified.toolkit, method, enabledToolkits(env)) || classified.hidden) return PASS;
    const windows = await listWindows(service);
    const current = Array.isArray(windows) ? windows.find(window => window.id === target.id) : null;
    if (!current) return PASS; // the original service reports its normal error
    const points = pointsOf(method, input, current);
    if (points === null) return PASS;
    const dialog = classified.toolkit === 'gtk4' ? await modalChild(current, windows) : null;
    if (dialog && !keyboard) {
      // The dialog's toolkit grab discards pointer input for its parent, and the parent's coordinates do
      // not describe the dialog; refuse rather than guess a position.
      throw new Rejection(`The window "${current.title}" has a modal dialog "${dialog.title}" (id ${dialog.id}) that grabs ` +
        'pointer input, so no input was sent. Target the dialog window explicitly with coordinates relative to it.');
    }
    requireInside(method, points, current);
    plan = {points, focus: dialog ?? current, screen: await screenSize()};
  } catch (error) {
    if (error instanceof Rejection) throw error;
    return PASS; // classification is best effort; never block the original behavior
  }

  const {points, focus, screen} = plan;
  if (!focus.focused) {
    await service.handleRpc({type: 'execute', method: 'activate_window', args: [{window: focus}]});
    await waitForFocus(service, focus.id);
  }
  // Read the geometry and the focus again immediately before sending: windows move, CSD shadows differ,
  // and anything else may have taken the focus since.
  const windows = await listWindows(service);
  const current = Array.isArray(windows) ? windows.find(window => window.id === target.id) : null;
  if (!current) throw new Rejection('The target window disappeared before its input could be sent.');
  if (!(Array.isArray(windows) ? windows.find(window => window.id === focus.id) : null)?.focused) {
    throw new Rejection('The keyboard focus left the target window before its input could be sent, so nothing was sent. ' +
      'Repeat the action.');
  }
  requireInside(method, points, current);
  const converted = desktopInput(method, input, current, points);
  if (outsideScreen(method, converted, screen)) return PASS; // an off-screen target keeps the original error

  if (method === 'key_down') {
    const tokens = chordTokens(input.key);
    if (!tokens) return PASS;
    const fresh = addOwners(tokens);
    let result = null;
    try {
      if (fresh.length) result = await service.handleRpc({type: 'execute', method, args: [{...converted, key: keyForTokens(fresh, tokens, input.key)}]});
    } catch (error) {
      dropOwners(tokens);
      throw error;
    }
    holds.push({targetId: target.id, chord: tokens.join('+')});
    return result;
  }
  return service.handleRpc({type: 'execute', method, args: [converted]});
}

function candidate(request) {
  if (request?.type !== 'execute' || typeof request.method !== 'string' ||
      !(KEY_METHODS.has(request.method) || POINTER_METHODS.has(request.method))) return false;
  const input = Array.isArray(request.args) && request.args.length === 1 ? request.args[0] : null;
  if (!input || !input.window || !Number.isInteger(input.window.id)) return false;
  return !KEY_METHODS.has(request.method) || typeof input.key === 'string';
}

export async function handleRpc(request) {
  const env = globalThis.nodeRepl?.env ?? process.env;
  original ??= import(pathToFileURL(env.LCU_LINUX_SKY_SERVICE_PATH).href);
  const service = await original;
  if (disabled(env) || !candidate(request)) return service.handleRpc(request);
  // One translated action at a time: planning, activation, geometry and input must not interleave.
  const run = queue.then(() => translate(service, request, env));
  queue = run.catch(() => {});
  const result = await run;
  return result === PASS ? service.handleRpc(request) : result;
}
