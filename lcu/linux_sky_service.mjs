// Forward the original Sky service unchanged, except for window-targeted input that the
// original Linux engine delivers with XSendEvent to toolkits that ignore it (GTK 4: press_key,
// clicks, scroll, drag and pointer moves; Qt: scroll). For those windows only, the same action is
// issued through the engine's own desktop-level call (XTEST) after the engine's own activate_window,
// with window-relative coordinates converted to desktop coordinates. No input is implemented here,
// and no key state is kept: key_down and key_up always go to the original service unchanged.
// A window is translated only when the X server itself says which local process owns it (the
// X-Resource extension, SO_PEERCRED on the server side) and that process is the one _NET_WM_PID
// names, in this PID namespace; anything else is left to the original service. Every call that can
// change focus or input state (translated or not: activate_window, desktop-level and window-targeted
// input of any kind, pass-through fallbacks) runs through one queue, so nothing interleaves between a
// translated request's final focus check and its input. Read-only calls bypass the queue. If the
// target cannot be focused, the point is outside the target, or the target owns a modal dialog and
// the input is a pointer action, a translated call fails with an explicit error and sends nothing.
import {pathToFileURL} from 'node:url';
import {execFile} from 'node:child_process';
import {readFile, readlink} from 'node:fs/promises';
import {hostname} from 'node:os';

const TOOLKIT_TTL_MS = 10_000;
const ACTIVATE_DEADLINE_MS = 1500;
const ACTIVATE_POLL_MS = 40;
const XPROP_TIMEOUT_MS = 3000;
const XRES_TIMEOUT_MS = 3000;
const DEFAULT_TOOLKITS = 'gtk4,qt-scroll';
// Windows of these runtimes handle XSendEvent themselves even if they map a GTK 4 library
// (Chromium and Electron mmap icudtl.dat; Firefox is libxul).
const NOT_GTK4 = [/\/icudtl\.dat/, /\/libxul\.so/, /\/libffmpeg\.so/];

// The local process the X server itself attributes to a window's client: XResQueryClientIds with
// XRES_CLIENT_ID_PID_MASK (X-Resource 1.2) returns the SO_PEERCRED process id of the connection and
// nothing for a client on another machine. Minimal ctypes use of libX11 and libXRes (Debian/Ubuntu
// package libxres1); it prints one process id, or nothing, and every failure means "unknown".
const XRES_PID_SCRIPT = `
import ctypes, sys
class Spec(ctypes.Structure):
    _fields_ = [('client', ctypes.c_ulong), ('mask', ctypes.c_uint)]
class Value(ctypes.Structure):
    _fields_ = [('spec', Spec), ('length', ctypes.c_long), ('value', ctypes.c_void_p)]
x11 = ctypes.CDLL('libX11.so.6')
xres = ctypes.CDLL('libXRes.so.1')
x11.XOpenDisplay.restype = ctypes.c_void_p
x11.XOpenDisplay.argtypes = [ctypes.c_char_p]
xres.XResQueryExtension.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int)]
xres.XResQueryVersion.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int)]
xres.XResQueryClientIds.argtypes = [ctypes.c_void_p, ctypes.c_long, ctypes.POINTER(Spec),
                                    ctypes.POINTER(ctypes.c_long), ctypes.POINTER(ctypes.POINTER(Value))]
xres.XResGetClientPid.argtypes = [ctypes.POINTER(Value)]
xres.XResGetClientPid.restype = ctypes.c_int
xres.XResClientIdsDestroy.argtypes = [ctypes.c_long, ctypes.POINTER(Value)]
display = x11.XOpenDisplay(None)
if not display:
    sys.exit(1)
a, b = ctypes.c_int(), ctypes.c_int()
if not xres.XResQueryExtension(display, ctypes.byref(a), ctypes.byref(b)):
    sys.exit(1)
if not xres.XResQueryVersion(display, ctypes.byref(a), ctypes.byref(b)) or (a.value, b.value) < (1, 2):
    sys.exit(1)
spec = Spec(int(sys.argv[1]), 1 << 1)
count = ctypes.c_long()
values = ctypes.POINTER(Value)()
if xres.XResQueryClientIds(display, 1, ctypes.byref(spec), ctypes.byref(count), ctypes.byref(values)) != 0:  # Success is 0
    sys.exit(1)
pids = {xres.XResGetClientPid(ctypes.byref(values[i])) for i in range(count.value)}
xres.XResClientIdsDestroy(count, values)
pids.discard(-1)
if len(pids) == 1:
    print(pids.pop())
`;

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
  xresPid: windowId => new Promise(resolve => {
    execFile('python3', ['-c', XRES_PID_SCRIPT, String(windowId)], {timeout: XRES_TIMEOUT_MS, maxBuffer: 1 << 12},
      (error, stdout) => {
        const pid = Number(String(stdout).trim());
        resolve(!error && Number.isInteger(pid) && pid > 0 ? pid : null);
      });
  }),
};

let original;
let queue = Promise.resolve();
const toolkitByPid = new Map();
const PASS = Symbol('pass');

// Atomic chords are translated; key_down and key_up never are (the original engine owns held keys).
const KEY_METHODS = new Set(['press_key']);
// Calls that neither move focus nor change input state; everything else (including unknown methods) is queued.
const READ_ONLY_METHODS = new Set(['list_windows', 'list_apps', 'get_screenshot', 'get_window_state']);
const POINTER_METHODS = new Set(['click', 'scroll', 'drag', 'move']);

class Rejection extends Error {}

export function resetForTests() {
  original = undefined;
  queue = Promise.resolve();
  toolkitByPid.clear();
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

// _NET_WM_PID is the client's own claim, in the client's PID namespace and on the client's machine (EWMH).
// It identifies a local process only when the X server's record agrees (see classify) and this process
// shares the process's PID namespace, so a window from another namespace is never classified.
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

// The toolkit is trusted only if the X server's own record of the window's client (a local process id
// from SO_PEERCRED, absent for remote clients) equals _NET_WM_PID. Otherwise the window may belong to
// a process in another PID namespace (Flatpak, containers) whose advertised id collides with an
// unrelated local process, or to a remote client, and the request is left to the original service.
async function classify(id) {
  const properties = await windowProperties(id);
  if (!properties.pid || !sameHost(properties.machine)) return {...properties, toolkit: null};
  const toolkit = await detectToolkit(properties.pid);
  if (!toolkit) return {...properties, toolkit: null};
  let authoritative = null;
  try { authoritative = await deps.xresPid(id); } catch { /* unknown */ }
  return {...properties, toolkit: authoritative === properties.pid ? toolkit : null};
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

// Runs inside the serialized queue: the window list, the modal state and the focus are read for this
// request only after every earlier queued call (translated or not) has finished.
async function translate(service, request, env) {
  const {method} = request;
  const input = request.args[0];
  const target = input.window;
  const keyboard = KEY_METHODS.has(method);

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

  return service.handleRpc({type: 'execute', method, args: [converted]});
}

function candidate(request) {
  if (request?.type !== 'execute' || typeof request.method !== 'string' ||
      !(KEY_METHODS.has(request.method) || POINTER_METHODS.has(request.method))) return false;
  const input = Array.isArray(request.args) && request.args.length === 1 ? request.args[0] : null;
  if (!input || !input.window || !Number.isInteger(input.window.id)) return false;
  return !KEY_METHODS.has(request.method) || typeof input.key === 'string';
}

function readOnly(request) {
  return request?.type === 'execute' && READ_ONLY_METHODS.has(request.method);
}

export async function handleRpc(request) {
  const env = globalThis.nodeRepl?.env ?? process.env;
  original ??= import(pathToFileURL(env.LCU_LINUX_SKY_SERVICE_PATH).href);
  const service = await original;
  if (disabled(env) || readOnly(request)) return service.handleRpc(request);
  // One input or focus-changing call at a time, translated or not: planning, activation, the final focus
  // check and the input of a translated request must not interleave with any other such call, including
  // activate_window, desktop-level input and the fallbacks below.
  const run = queue.then(async () => {
    if (candidate(request)) {
      const result = await translate(service, request, env);
      if (result !== PASS) return result;
    }
    return service.handleRpc(request);
  });
  queue = run.catch(() => {});
  return run;
}
