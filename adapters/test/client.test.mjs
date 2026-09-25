import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createCuaClient, nativeAppApprovalOptions, nativeAppApprovalResponse } from '../client.mjs';

const command = [process.execPath, new URL('./mcp-fixture.mjs', import.meta.url).pathname];

const nativeApproval = (persist = ['session', 'always']) => ({
  mode: 'form',
  message: 'Allow Computer Use to use "LCU Fixture App"?',
  requestedSchema: { type: 'object', properties: {} },
  _meta: {
    codex_approval_kind: 'mcp_tool_call',
    connector_id: 'computer-use',
    persist,
    tool_name: 'get_app_state',
    tool_params: { app: 'dev.lcu.NativeFixture.generated' },
  },
});

test('keeps original tool descriptors and initialization instructions; hides internal tools', async () => {
  const bridge = createCuaClient({ command });
  try {
    await bridge.connect();
    assert.equal(bridge.instructions, 'Original CUA initialization guide.');
    assert.deepEqual(bridge.publicTools().map(tool => tool.name), ['js', 'js_reset']);
    assert.equal(bridge.publicTools()[0].description, 'Original JS description.');
    assert.deepEqual(bridge.publicTools()[0].inputSchema.required, ['code']);
    await assert.rejects(bridge.call('turn_ended', {}, { sessionId: 's', turnId: 't' }), /reserved/);
    await assert.rejects(bridge.call('js', { code: 'x' }), /real host session/);
    const result = await bridge.call('js', { code: 'x' }, { sessionId: 'real-session', turnId: 'real-turn' });
    assert.deepEqual(result.content, [{ type: 'text', text: 'x' }]);
    await bridge.turnEnded({ sessionId: 'real-session', turnId: 'real-turn' });
    await assert.rejects(bridge.turnEnded({ sessionId: 'fail-session', turnId: 'real-turn' }),
      /cleanup failed/);
  } finally { await bridge.close(); }
});

test('elicitation is denied by default and exact authorized origins are accepted', async () => {
  for (const [allowedOrigins, expected] of [
    [[], 'cancel'], [['http://127.0.0.1:8080'], 'accept'],
  ]) {
    const bridge = createCuaClient({ command, allowedOrigins });
    try {
      await bridge.connect();
      const result = await bridge.call('js', { code: 'approval' }, { sessionId: 's', turnId: 't' });
      assert.equal(result.content[0].text, expected);
    } finally { await bridge.close(); }
  }
  const seen = [];
  const bridge = createCuaClient({ command, allowedOrigins: ['https://different.example'],
    onElicitation: async params => { seen.push(params); return { action: 'decline' }; } });
  try {
    await bridge.connect();
    const result = await bridge.call('js', { code: 'approval' }, { sessionId: 's', turnId: 't' });
    assert.equal(result.content[0].text, 'decline');
    assert.equal(seen.length, 1);
    assert.equal(seen[0]._meta.origin, 'http://127.0.0.1:8080');
  } finally { await bridge.close(); }
  assert.throws(() => createCuaClient({ command, allowedOrigins: ['http://127.0.0.1:8080/'] }), /exact HTTP/);
});

test('native app approval choices preserve resource identity and only offered persistence scopes', () => {
  const request = nativeApproval();
  const options = nativeAppApprovalOptions(request);
  assert.deepEqual(options, {
    message: request.message,
    resource: 'dev.lcu.NativeFixture.generated',
    choices: [
      { value: 'once', label: 'Allow once' },
      { value: 'session', label: 'Allow for this session' },
      { value: 'always', label: 'Always allow' },
      { value: 'decline', label: 'Decline' },
    ],
  });
  assert.deepEqual(nativeAppApprovalResponse(request, 'once'), { action: 'accept', content: {} });
  assert.deepEqual(nativeAppApprovalResponse(request, 'session'), {
    action: 'accept', content: {}, _meta: { persist: 'session' },
  });
  assert.deepEqual(nativeAppApprovalResponse(request, 'always'), {
    action: 'accept', content: {}, _meta: { persist: 'always' },
  });
  assert.deepEqual(nativeAppApprovalResponse(request, 'decline'), { action: 'decline' });
  assert.deepEqual(nativeAppApprovalResponse(request, 'cancel'), { action: 'cancel' });

  const sessionOnly = nativeApproval(['session']);
  assert.deepEqual(nativeAppApprovalOptions(sessionOnly).choices.map(choice => choice.value),
    ['once', 'session', 'decline']);
  assert.deepEqual(nativeAppApprovalResponse(sessionOnly, 'always'), { action: 'cancel' });
  assert.deepEqual(nativeAppApprovalResponse(nativeApproval([]), 'session'), { action: 'cancel' });
});

test('native app approval classifier leaves unrelated or unsupported elicitations unchanged', () => {
  const base = nativeApproval();
  for (const params of [
    { ...base, mode: 'url' },
    { ...base, requestedSchema: { type: 'object', properties: { secret: { type: 'string' } } } },
    { ...base, _meta: { ...base._meta, connector_id: 'browser' } },
    { ...base, _meta: { ...base._meta, tool_params: {} } },
    { mode: 'form', message: 'Other empty form', requestedSchema: { type: 'object', properties: {} }, _meta: {} },
  ]) {
    assert.equal(nativeAppApprovalOptions(params), undefined);
    assert.deepEqual(nativeAppApprovalResponse(params, 'always'), { action: 'cancel' });
  }
  const malformedScopes = { ...base, _meta: { ...base._meta, persist: 'always' } };
  assert.deepEqual(nativeAppApprovalOptions(malformedScopes).choices.map(choice => choice.value),
    ['once', 'decline']);
  assert.deepEqual(nativeAppApprovalResponse(malformedScopes, 'always'), { action: 'cancel' });
});
