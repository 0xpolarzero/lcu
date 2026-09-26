import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, isAbsolute, join } from 'node:path';
import piExtension from '../pi/index.ts';

const fixture = new URL('./mcp-fixture.mjs', import.meta.url).pathname;

test('Pi keeps one original CUA turn across model rounds and cleans up after agent_end', async () => {
  const directory = mkdtempSync(join(tmpdir(), 'lcu-pi-'));
  const log = join(directory, 'mcp.jsonl');
  const oldCommand = process.env.LCU_MCP_COMMAND;
  const oldLog = process.env.LCU_FIXTURE_LOG;
  process.env.LCU_MCP_COMMAND = JSON.stringify([process.execPath, fixture]);
  process.env.LCU_FIXTURE_LOG = log;
  const handlers = new Map();
  const tools = new Map();
  let audioDirectory;
  const pi = {
    on(event, handler) { handlers.set(event, handler); },
    registerTool(tool) { tools.set(tool.name, tool); },
  };
  const ctx = { sessionManager: { getSessionId: () => 'pi-real-session' },
    model: { id: 'pi-model' }, hasUI: false };
  try {
    piExtension(pi);
    const prompt = await handlers.get('before_agent_start')({ systemPrompt: 'Pi base prompt' }, ctx);
    assert.match(prompt.systemPrompt, /Original CUA initialization guide/);
    assert.deepEqual([...tools.keys()], ['js', 'js_reset']);
    assert.equal(tools.get('js').description, 'Original JS description.');
    assert.deepEqual(tools.get('js').parameters.required, ['code']);
    await handlers.get('agent_start')({}, ctx);
    const first = await tools.get('js').execute('1', { code: 'first' }, undefined, undefined, ctx);
    assert.equal(first.content[0].text, 'first');
    // Pi emits turn_end after each assistant/model round. LCU cleanup belongs
    // to agent_end, so this event has no adapter handler.
    assert.equal(handlers.has('turn_end'), false);
    const second = await tools.get('js').execute('2', { code: 'second' }, undefined, undefined, ctx);
    assert.equal(second.content[0].text, 'second');
    const audio = await tools.get('js').execute('3', { code: 'audio' }, undefined, undefined, ctx);
    assert.equal('isError' in audio, false);
    assert.match(audio.content[0].text, /original MIME type: audio\/wav/);
    const audioPath = /saved to (.+)$/.exec(audio.content[0].text)?.[1];
    assert.ok(audioPath);
    assert.equal(isAbsolute(audioPath), true);
    assert.deepEqual(readFileSync(audioPath), Buffer.from('AAAA', 'base64'));
    audioDirectory = dirname(audioPath);
    let entries = readFileSync(log, 'utf8').trim().split('\n').map(JSON.parse);
    assert.equal(entries.some(entry => entry.name === 'turn_ended'), false);
    assert.equal(entries[0].meta['x-codex-turn-metadata'].session_id, 'pi-real-session');
    assert.equal(entries[0].meta['x-codex-turn-metadata'].turn_id,
      entries[1].meta['x-codex-turn-metadata'].turn_id);
    assert.equal(entries[0].meta['x-codex-turn-metadata'].model, 'pi-model');
    await handlers.get('agent_end')({ messages: [{ role: 'assistant', stopReason: 'stop' }] }, ctx);
    entries = readFileSync(log, 'utf8').trim().split('\n').map(JSON.parse);
    const ended = entries.filter(entry => entry.name === 'turn_ended');
    assert.equal(ended.length, 1);
    assert.deepEqual(ended[0].args, {
      hook_event_name: 'Stop', session_id: 'pi-real-session',
      turn_id: entries[0].meta['x-codex-turn-metadata'].turn_id,
    });
    await handlers.get('session_shutdown')();
  } finally {
    await handlers.get('session_shutdown')?.();
    if (audioDirectory) rmSync(audioDirectory, { recursive: true, force: true });
    if (oldCommand === undefined) delete process.env.LCU_MCP_COMMAND;
    else process.env.LCU_MCP_COMMAND = oldCommand;
    if (oldLog === undefined) delete process.env.LCU_FIXTURE_LOG;
    else process.env.LCU_FIXTURE_LOG = oldLog;
    rmSync(directory, { recursive: true, force: true });
  }
});

test('Pi asks for non-origin empty-form approval and cancels unsupported forms', async () => {
  const oldCommand = process.env.LCU_MCP_COMMAND;
  process.env.LCU_MCP_COMMAND = JSON.stringify([process.execPath, fixture]);
  const handlers = new Map();
  const tools = new Map();
  const prompts = [];
  const pi = { on(event, handler) { handlers.set(event, handler); },
    registerTool(tool) { tools.set(tool.name, tool); } };
  const ctx = { sessionManager: { getSessionId: () => 'pi-approval-session' },
    model: { id: 'pi-model' }, hasUI: true,
    ui: { async select(title, options) { prompts.push([title, options]); return 'Allow'; } } };
  try {
    piExtension(pi);
    await handlers.get('before_agent_start')({ systemPrompt: 'Pi' }, ctx);
    await handlers.get('agent_start')({}, ctx);
    const native = await tools.get('js').execute('1', { code: 'approval-other' }, undefined, undefined, ctx);
    assert.equal(native.content[0].text, 'accept');
    assert.deepEqual(prompts, [['Allow native window access?', ['Allow', 'Decline']]]);
    const form = await tools.get('js').execute('2', { code: 'approval-form' }, undefined, undefined, ctx);
    assert.equal(form.content[0].text, 'cancel');
    assert.equal(prompts.length, 1);
    await handlers.get('agent_end')({ messages: [{ role: 'assistant', stopReason: 'aborted' }] }, ctx);
  } finally {
    await handlers.get('session_shutdown')?.();
    if (oldCommand === undefined) delete process.env.LCU_MCP_COMMAND;
    else process.env.LCU_MCP_COMMAND = oldCommand;
  }
});

test('Pi forwards only the native app approval persistence scope selected in its UI', async () => {
  const oldCommand = process.env.LCU_MCP_COMMAND;
  process.env.LCU_MCP_COMMAND = JSON.stringify([process.execPath, fixture]);
  const handlers = new Map();
  const tools = new Map();
  const prompts = [];
  let selection = 'Allow for this session';
  const pi = { on(event, handler) { handlers.set(event, handler); }, registerTool(tool) { tools.set(tool.name, tool); } };
  const ctx = { sessionManager: { getSessionId: () => 'pi-native-approval-session' },
    model: { id: 'pi-model' }, hasUI: true,
    ui: {
      async select(title, options) { prompts.push({ title, options }); return selection; },
      async confirm() { assert.fail('Native app requests use the scope selector'); },
    } };
  try {
    piExtension(pi);
    await handlers.get('before_agent_start')({ systemPrompt: 'Pi' }, ctx);
    await handlers.get('agent_start')({}, ctx);
    const execute = async (code, id) => {
      const result = await tools.get('js').execute(id, { code }, undefined, undefined, ctx);
      return JSON.parse(result.content[0].text);
    };
    const session = await execute('approval-native', 'native-session');
    assert.deepEqual(session, { action: 'accept', content: {}, _meta: { persist: 'session' } });
    assert.deepEqual(prompts.at(-1), {
      title: 'Allow Computer Use to use "LCU Fixture App"?',
      options: ['Allow once', 'Allow for this session', 'Always allow', 'Decline'],
    });

    selection = 'Always allow';
    const always = await execute('approval-native', 'native-always');
    assert.deepEqual(always, { action: 'accept', content: {}, _meta: { persist: 'always' } });

    selection = 'Allow once';
    const once = await execute('approval-native', 'native-once');
    assert.deepEqual(once, { action: 'accept', content: {} });

    selection = 'Always allow';
    const forbidden = await execute('approval-native-session-only', 'native-forbidden-scope');
    assert.deepEqual(forbidden, { action: 'cancel' });
    assert.deepEqual(prompts.at(-1).options, ['Allow once', 'Allow for this session', 'Decline']);

    selection = 'Decline';
    assert.deepEqual(await execute('approval-native', 'native-decline'), { action: 'decline' });
    selection = undefined;
    assert.deepEqual(await execute('approval-native', 'native-cancel'), { action: 'cancel' });
    assert.equal(prompts.length, 6);
    await handlers.get('agent_end')({ messages: [{ role: 'assistant', stopReason: 'stop' }] }, ctx);
  } finally {
    await handlers.get('session_shutdown')?.();
    if (oldCommand === undefined) delete process.env.LCU_MCP_COMMAND;
    else process.env.LCU_MCP_COMMAND = oldCommand;
  }
});

test('Pi closes its MCP connection after a reported cleanup failure', async () => {
  const oldCommand = process.env.LCU_MCP_COMMAND;
  process.env.LCU_MCP_COMMAND = JSON.stringify([process.execPath, fixture]);
  const handlers = new Map();
  const pi = { on(event, handler) { handlers.set(event, handler); }, registerTool() {} };
  const ctx = { sessionManager: { getSessionId: () => 'fail-session' }, hasUI: false };
  try {
    piExtension(pi);
    await handlers.get('before_agent_start')({ systemPrompt: 'Pi' }, ctx);
    await handlers.get('agent_start')({}, ctx);
    await assert.rejects(handlers.get('session_shutdown')(), /cleanup failed/);
    await handlers.get('session_shutdown')();
  } finally {
    if (oldCommand === undefined) delete process.env.LCU_MCP_COMMAND;
    else process.env.LCU_MCP_COMMAND = oldCommand;
  }
});
