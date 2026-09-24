import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
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
    await assert.rejects(tools.get('js').execute('3', { code: 'audio' }, undefined, undefined, ctx),
      /cannot represent original CUA audio content/);
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
    ui: { async confirm(title, message) { prompts.push([title, message]); return true; } } };
  try {
    piExtension(pi);
    await handlers.get('before_agent_start')({ systemPrompt: 'Pi' }, ctx);
    await handlers.get('agent_start')({}, ctx);
    const native = await tools.get('js').execute('1', { code: 'approval-other' }, undefined, undefined, ctx);
    assert.equal(native.content[0].text, 'accept');
    assert.deepEqual(prompts, [['LCU approval', 'Allow native window access?']]);
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
