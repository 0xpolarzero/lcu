import { appendFileSync } from 'node:fs';
import { Server } from '@modelcontextprotocol/sdk/server/index.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import { CallToolRequestSchema, ListToolsRequestSchema } from '@modelcontextprotocol/sdk/types.js';

const server = new Server({ name: 'original-cua-contract-fixture', version: '1' },
  { capabilities: { tools: {} }, instructions: 'Original CUA initialization guide.' });
const record = value => process.env.LCU_FIXTURE_LOG && appendFileSync(process.env.LCU_FIXTURE_LOG, `${JSON.stringify(value)}\n`);
server.setRequestHandler(ListToolsRequestSchema, async () => ({ tools: [
  { name: 'js', description: 'Original JS description.', inputSchema: {
    type: 'object', properties: { code: { type: 'string' } }, required: ['code'], additionalProperties: false,
  } },
  { name: 'js_reset', description: 'Original reset description.', inputSchema: {
    type: 'object', properties: {}, additionalProperties: false,
  } },
  { name: 'js_add_node_module_dir', description: 'Internal.', inputSchema: { type: 'object' } },
  { name: 'turn_ended', description: 'Internal.', inputSchema: { type: 'object' } },
] }));
server.setRequestHandler(CallToolRequestSchema, async request => {
  const { name, arguments: args, _meta } = request.params;
  record({ name, args, meta: _meta });
  if (name === 'turn_ended' && args?.session_id === 'fail-session') {
    return { isError: true, content: [{ type: 'text', text: 'cleanup failed' }] };
  }
  if (name === 'js' && ['approval', 'approval-other', 'approval-form'].includes(args?.code)) {
    const browser = args.code === 'approval';
    const form = args.code === 'approval-form';
    const decision = await server.elicitInput({
      message: browser ? 'Allow Browser use to access http://127.0.0.1:8080?' :
        form ? 'Enter a secret' : 'Allow native window access?',
      _meta: browser ? { tool_name: 'access_browser_origin', origin: 'http://127.0.0.1:8080' } : {},
      requestedSchema: { type: 'object', properties: form ? { secret: { type: 'string' } } : {} },
    });
    return { content: [{ type: 'text', text: decision.action }] };
  }
  if (name === 'js' && args?.code === 'audio') {
    return { content: [{ type: 'audio', data: 'AAAA', mimeType: 'audio/wav' }] };
  }
  return { content: [{ type: 'text', text: name === 'js' ? String(args?.code) : name }] };
});
await server.connect(new StdioServerTransport());
