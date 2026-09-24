import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createCuaClient } from '../client.mjs';

const command = [process.execPath, new URL('./mcp-fixture.mjs', import.meta.url).pathname];

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
