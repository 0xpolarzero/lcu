// In-memory regression tests for lcu/linux_sky_service.mjs. A fake desktop stands in for the original Sky
// service (window list, focus, desktop-level input with a held-key model) and for xprop and /proc, so
// every decision of the wrapper is observable without an X server. Desktop behavior is covered by
// tests/gtk4_input.py and tests/linux_input_controls.py.
import assert from 'node:assert/strict';
import {mkdtempSync, rmSync, writeFileSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {afterEach, beforeEach, test} from 'node:test';
import {pathToFileURL} from 'node:url';
import * as wrapper from '../../lcu/linux_sky_service.mjs';

const GTK4_MAPS = '7f00 r-xp /usr/lib/x86_64-linux-gnu/libgtk-4.so.1\n';
const QT_MAPS = '7f00 r-xp /usr/lib/x86_64-linux-gnu/libQt6Core.so.6\n';
const PLAIN_MAPS = '7f00 r-xp /usr/lib/x86_64-linux-gnu/libc.so.6\n';
const HOST = 'lcu-test-host';
const sleepOnly = () => Promise.resolve();

let directory;
let desk;
const savedEnv = {};

class Desktop {
  constructor() {
    this.windows = [];
    this.procs = new Map(); // pid -> {maps, start, ns}
    this.calls = [];        // everything the original service received, in order
    this.typed = [];
    this.down = new Set();
    this.activations = 0;
    this.afterActivate = null;
    this.listsAfterActivate = 0;
    this.stealAfterFirstList = null;
    this.hostname = HOST;
    this.ns = 'pid:[4026531836]';
  }

  add(id, fields = {}) {
    const window = {id, x: 100, y: 80, width: 300, height: 200, focused: false, modal: false, window_type: 'normal',
      title: `w${id}`, app: `x11:${id}`, ...fields};
    this.windows.push(window);
    if (!this.procs.has(window.pid ?? id)) this.procs.set(window.pid ?? id, {maps: GTK4_MAPS, start: 1000 + id, ns: this.ns});
    return window;
  }

  focus(id) {
    for (const window of this.windows) window.focused = window.id === id;
  }

  focusedId() {
    return this.windows.find(window => window.focused)?.id ?? null;
  }

  view() {
    return this.windows.map(({pid, transientFor, hidden, machine, ...rest}) => ({...rest}));
  }

  async handleRpc(request) {
    this.calls.push(request);
    const {method, args = []} = request;
    const input = args[0] ?? {};
    if (method === 'list_windows') {
      if (this.activations > 0 && this.stealAfterFirstList) {
        this.listsAfterActivate += 1;
        if (this.listsAfterActivate === 2) this.focus(this.stealAfterFirstList);
      }
      return this.view();
    }
    if (method === 'activate_window') {
      this.activations += 1;
      await new Promise(resolve => setImmediate(resolve)); // activation takes a moment under a real WM
      this.focus(input.window.id);
      if (this.afterActivate) this.afterActivate(input.window.id);
      return null;
    }
    if (input.window) return {targeted: true};
    if (method === 'key_down') { for (const key of input.key.split('+')) this.down.add(key.toLowerCase()); }
    else if (method === 'key_up') { for (const key of input.key.split('+')) this.down.delete(key.toLowerCase()); }
    else if (method === 'press_key') {
      const upper = this.down.has('shift') || this.down.has('shift_l');
      this.typed.push({key: upper ? input.key.toUpperCase() : input.key, windowId: this.focusedId()});
    }
    return {desktop: true};
  }

  desktopCalls(...methods) {
    return this.calls.filter(call => call.type === 'execute' && methods.includes(call.method) && !call.args?.[0]?.window);
  }

  targetedCalls() {
    return this.calls.filter(call => call.type === 'execute' && call.args?.[0]?.window && call.method !== 'activate_window');
  }
}

function installDeps() {
  wrapper.deps.sleep = sleepOnly;
  wrapper.deps.hostname = () => desk.hostname;
  wrapper.deps.xprop = async args => {
    if (args[0] === '-root') return '_NET_DESKTOP_GEOMETRY(CARDINAL) = 1280, 800\n';
    const id = Number(args[1]);
    const window = desk.windows.find(candidate => candidate.id === id);
    if (!window) throw Error('BadWindow');
    const lines = [];
    const pid = window.pid ?? id;
    if (!window.noPid) lines.push(`_NET_WM_PID(CARDINAL) = ${pid}`);
    lines.push(window.transientFor ? `WM_TRANSIENT_FOR(WINDOW): window id # 0x${window.transientFor.toString(16)}`
      : 'WM_TRANSIENT_FOR:  not found.');
    lines.push(`_NET_WM_STATE(ATOM) = ${window.hidden ? '_NET_WM_STATE_HIDDEN' : ''}`);
    const machine = window.machine === undefined ? HOST : window.machine;
    lines.push(machine === null ? 'WM_CLIENT_MACHINE:  not found.' : `WM_CLIENT_MACHINE(STRING) = "${machine}"`);
    return lines.join('\n') + '\n';
  };
  wrapper.deps.readFile = async path => {
    const match = /^\/proc\/(\d+)\/(maps|stat)$/.exec(path);
    const proc = match && desk.procs.get(Number(match[1]));
    if (!proc) throw Error('ENOENT');
    if (match[2] === 'maps') return proc.maps;
    const rest = Array.from({length: 17}, () => '0'); // fields 5..21
    return `${match[1]} (we ird) name) S 1 ${rest.join(' ')} ${proc.start} 0 0\n`;
  };
  wrapper.deps.readLink = async path => {
    if (path === '/proc/self/ns/pid') return desk.ns;
    const match = /^\/proc\/(\d+)\/ns\/pid$/.exec(path);
    const proc = match && desk.procs.get(Number(match[1]));
    if (!proc) throw Error('ENOENT');
    return proc.ns;
  };
}

beforeEach(() => {
  directory = mkdtempSync(join(tmpdir(), 'lcu-sky-'));
  const module = join(directory, 'service.mjs');
  writeFileSync(module, 'export const handleRpc = request => globalThis.__lcuFakeSky.handleRpc(request);\n');
  for (const key of ['LCU_LINUX_SKY_SERVICE_PATH', 'LCU_LINUX_INPUT_TRANSLATION', 'LCU_LINUX_INPUT_TOOLKITS']) savedEnv[key] = process.env[key];
  process.env.LCU_LINUX_SKY_SERVICE_PATH = module;
  delete process.env.LCU_LINUX_INPUT_TRANSLATION;
  delete process.env.LCU_LINUX_INPUT_TOOLKITS;
  desk = new Desktop();
  globalThis.__lcuFakeSky = desk;
  wrapper.resetForTests();
  installDeps();
});

afterEach(() => {
  rmSync(directory, {recursive: true, force: true});
  for (const [key, value] of Object.entries(savedEnv)) {
    if (value === undefined) delete process.env[key]; else process.env[key] = value;
  }
  delete globalThis.__lcuFakeSky;
});

const execute = (method, input) => wrapper.handleRpc({type: 'execute', method, args: [input]});
const target = window => ({id: window.id, app: window.app, title: window.title, x: window.x, y: window.y,
  width: window.width, height: window.height, focused: window.focused, modal: window.modal, window_type: 'normal'});

test('concurrent keys to two windows each reach their own window', async () => {
  const a = desk.add(1);
  const b = desk.add(2);
  desk.focus(1);
  const staleA = target(a); // the caller's snapshot says A is focused
  await Promise.all([execute('press_key', {window: target(b), key: 'b'}), execute('press_key', {window: staleA, key: 'a'})]);
  assert.deepEqual(desk.typed, [{key: 'b', windowId: 2}, {key: 'a', windowId: 1}]);
});

test('focus that moves away before the input is sent rejects the call and sends nothing', async () => {
  desk.add(1);
  desk.add(2);
  desk.add(3);
  desk.focus(3);
  desk.stealAfterFirstList = 3; // the second listing after activation shows another window focused
  await assert.rejects(execute('press_key', {window: target(desk.windows[0]), key: 'x'}), /focus/i);
  assert.deepEqual(desk.typed, []);
  assert.equal(desk.desktopCalls('press_key').length, 0);
});

test('translated key holds are released at the desktop even after the target closes', async () => {
  const a = desk.add(1);
  desk.focus(1);
  await execute('key_down', {window: target(a), key: 'shift'});
  assert.ok(desk.down.has('shift'));
  desk.windows = []; // the target closed
  await execute('key_up', {window: target(a), key: 'shift'});
  assert.equal(desk.down.size, 0, 'the desktop hold was left active');
  assert.equal(desk.targetedCalls().length, 0, 'the release must not become a window-targeted no-op');
  const b = desk.add(2);
  desk.focus(2);
  await execute('press_key', {window: target(b), key: 'k'});
  assert.deepEqual(desk.typed, [{key: 'k', windowId: 2}], 'a later key came out shifted');
});

test('a hold released for a minimized target still releases the desktop key', async () => {
  const a = desk.add(1);
  desk.focus(1);
  await execute('key_down', {window: target(a), key: 'ctrl'});
  a.hidden = true;
  await execute('key_up', {window: target(a), key: 'ctrl'});
  assert.equal(desk.down.size, 0);
});

test('overlapping holds of the same key keep the desktop key down until the last owner releases', async () => {
  const a = desk.add(1);
  const b = desk.add(2);
  desk.focus(1);
  await execute('key_down', {window: target(a), key: 'Shift'});
  await execute('key_down', {window: target(b), key: 'shift'});
  await execute('key_up', {window: target(a), key: 'shift'});
  assert.ok(desk.down.has('shift'), "A's release dropped B's hold");
  await execute('press_key', {window: target(b), key: 'k'});
  assert.equal(desk.typed.at(-1).key, 'K');
  await execute('key_up', {window: target(b), key: 'Shift'});
  assert.equal(desk.down.size, 0);
});

test('a duplicate hold by the same target needs both releases', async () => {
  const a = desk.add(1);
  desk.focus(1);
  await execute('key_down', {window: target(a), key: 'shift'});
  await execute('key_down', {window: target(a), key: 'shift'});
  await execute('key_up', {window: target(a), key: 'shift'});
  assert.ok(desk.down.has('shift'));
  await execute('key_up', {window: target(a), key: 'shift'});
  assert.equal(desk.down.size, 0);
});

test('a release that matches no translated hold never reaches the desktop level', async () => {
  const a = desk.add(1);
  const b = desk.add(2);
  desk.focus(1);
  await execute('key_down', {window: target(a), key: 'shift'});
  await execute('key_up', {window: target(b), key: 'shift'});
  assert.ok(desk.down.has('shift'), "B never held shift; its release must not drop A's hold");
  await execute('key_up', {window: target(a), key: 'shift'});
  assert.equal(desk.down.size, 0);
});

test('chords share modifiers by owner', async () => {
  const a = desk.add(1);
  const b = desk.add(2);
  desk.focus(1);
  await execute('key_down', {window: target(a), key: 'ctrl+shift'});
  await execute('key_down', {window: target(b), key: 'shift'});
  await execute('key_up', {window: target(a), key: 'ctrl+shift'});
  assert.deepEqual([...desk.down], ['shift']);
  await execute('key_up', {window: target(b), key: 'shift'});
  assert.equal(desk.down.size, 0);
});

test('points outside the target window are rejected instead of clicking another application', async () => {
  const a = desk.add(1); // client 300x200 at 100,80
  desk.focus(1);
  for (const [method, input] of [
    ['click', {x: 350, y: 50}], ['click', {x: -1, y: 5}], ['click', {x: 10, y: 200}],
    ['move', {x: 300, y: 10}], ['scroll', {x: 10, y: 500, direction: 'down', pixels: 10}],
    ['drag', {path: [{x: 400, y: 10}, {x: 20, y: 20}]}],
  ]) {
    await assert.rejects(execute(method, {window: target(a), ...input}), /outside/i, method);
  }
  assert.equal(desk.desktopCalls('click', 'move', 'scroll', 'drag').length, 0);
  await execute('click', {window: target(a), x: 299, y: 199});
  assert.deepEqual(desk.desktopCalls('click')[0].args[0], {x: 399, y: 279});
});

test('a drag may end outside the target and is converted point by point', async () => {
  const a = desk.add(1);
  desk.focus(1);
  await execute('drag', {window: target(a), path: [{x: 10, y: 10}, {x: 340, y: 250}]});
  assert.deepEqual(desk.desktopCalls('drag')[0].args[0].path, [{x: 110, y: 90}, {x: 440, y: 330}]);
});

test('a point valid for the old geometry is rejected after the window shrank', async () => {
  const a = desk.add(1);
  desk.focus(2);
  desk.add(2);
  desk.focus(2);
  desk.afterActivate = () => { a.width = 100; a.height = 100; };
  await assert.rejects(execute('click', {window: target(a), x: 250, y: 150}), /outside/i);
  assert.equal(desk.desktopCalls('click').length, 0);
});

test('keyboard input to a window with a modal dialog goes to the dialog', async () => {
  const parent = desk.add(1);
  desk.add(2, {modal: true, transientFor: 1, title: 'dialog'});
  desk.focus(2);
  await execute('press_key', {window: target(parent), key: 'm'});
  assert.deepEqual(desk.typed, [{key: 'm', windowId: 2}]);
  assert.equal(desk.activations, 0);
});

test('pointer input to a window with a modal dialog is refused and names the dialog', async () => {
  const parent = desk.add(1);
  const dialog = desk.add(2, {modal: true, transientFor: 1, title: 'Save changes', x: 150, y: 120, width: 120, height: 60});
  desk.focus(2);
  for (const [method, input] of [['click', {x: 40, y: 40}], ['scroll', {direction: 'down', pixels: 5}],
    ['move', {x: 40, y: 40}], ['drag', {path: [{x: 1, y: 1}, {x: 9, y: 9}]}]]) {
    await assert.rejects(execute(method, {window: target(parent), ...input}), /modal.*Save changes/is, method);
  }
  assert.equal(desk.desktopCalls('click', 'scroll', 'move', 'drag').length, 0);
  await execute('click', {window: target(dialog), x: 10, y: 10});
  assert.deepEqual(desk.desktopCalls('click')[0].args[0], {x: 160, y: 130});
});

test('a reused process id does not inherit the earlier toolkit', async () => {
  const a = desk.add(1, {pid: 500});
  desk.focus(1);
  await execute('press_key', {window: target(a), key: 'a'});
  assert.equal(desk.typed.length, 1, 'the GTK 4 process is translated');
  // The process exits and another program reuses the id within the cache lifetime.
  desk.procs.set(500, {maps: PLAIN_MAPS, start: 99999, ns: desk.ns});
  await execute('press_key', {window: target(a), key: 'b'});
  assert.equal(desk.typed.length, 1, 'the new process must not be translated');
  assert.equal(desk.targetedCalls().length, 1);
});

test('a process whose start time changes during detection is treated as unknown', async () => {
  const a = desk.add(1);
  desk.focus(1);
  let reads = 0;
  const original = wrapper.deps.readFile;
  wrapper.deps.readFile = async path => {
    if (path.endsWith('/stat') && ++reads === 2) desk.procs.get(1).start += 1;
    return original(path);
  };
  await execute('press_key', {window: target(a), key: 'a'});
  assert.equal(desk.typed.length, 0);
  assert.equal(desk.targetedCalls().length, 1);
});

test('windows owned by another machine, PID namespace or without a client machine are left untouched', async () => {
  const foreign = desk.add(1, {machine: 'remote-box'});
  const unnamed = desk.add(2, {machine: null});
  const namespaced = desk.add(3);
  desk.procs.get(3).ns = 'pid:[4026532999]';
  const noPid = desk.add(4, {noPid: true});
  desk.focus(4);
  for (const window of [foreign, unnamed, namespaced, noPid]) {
    await execute('press_key', {window: target(window), key: 'z'});
  }
  assert.equal(desk.typed.length, 0);
  assert.equal(desk.targetedCalls().length, 4);
  assert.equal(desk.activations, 0);
  const local = desk.add(5, {machine: HOST.toUpperCase()});
  await execute('press_key', {window: target(local), key: 'z'});
  assert.equal(desk.typed.length, 1, 'a window of this machine, in any case, is still translated');
});

test('Qt is translated for scroll only', async () => {
  const qt = desk.add(1);
  desk.procs.get(1).maps = QT_MAPS;
  desk.focus(1);
  await execute('press_key', {window: target(qt), key: 'a'});
  assert.equal(desk.typed.length, 0);
  await execute('scroll', {window: target(qt), direction: 'down', pixels: 10});
  assert.equal(desk.desktopCalls('scroll').length, 1);
});

test('LCU_LINUX_INPUT_TRANSLATION=off sends everything to the original service unchanged', async () => {
  process.env.LCU_LINUX_INPUT_TRANSLATION = 'off';
  const a = desk.add(1);
  await execute('click', {window: target(a), x: 5000, y: 5000});
  await execute('press_key', {window: target(a), key: 'a'});
  assert.equal(desk.targetedCalls().length, 2);
  assert.equal(desk.activations, 0);
});

test('a window that is not listed keeps the original service result', async () => {
  desk.add(1);
  await execute('press_key', {window: {id: 99, app: 'x11:99', title: 'gone'}, key: 'a'});
  assert.equal(desk.targetedCalls().length, 1);
});
