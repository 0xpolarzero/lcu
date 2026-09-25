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
  if (name === 'js' && ['approval', 'approval-other', 'approval-form', 'approval-native',
    'approval-native-session-only', 'pi-origin-approval', 'pi-origin-lookalike',
    'pi-origin-other-empty'].includes(args?.code)) {
    const browser = args.code === 'approval' || args.code === 'pi-origin-approval' ||
      args.code === 'pi-origin-lookalike';
    const piOrigin = args.code.startsWith('pi-origin-');
    const otherEmpty = args.code === 'pi-origin-other-empty';
    const origin = args.code === 'pi-origin-lookalike'
      ? 'http://127.0.0.1.attacker.invalid:8080' : 'http://127.0.0.1:8080';
    const form = args.code === 'approval-form';
    const native = args.code === 'approval-native' || args.code === 'approval-native-session-only';
    const decision = await server.elicitInput({
      message: browser ? `Allow Browser use to access ${origin}?` : otherEmpty
        ? 'Allow Browser use to use your browsing history for this task?' : form ? 'Enter a secret' :
          native ? 'Allow Computer Use to use "LCU Fixture App"?' : 'Allow native window access?',
      _meta: browser ? {
        codex_approval_kind: 'mcp_tool_call',
        codex_sensitive_action: true,
        connector_id: 'browser-use',
        connector_name: 'Browser use',
        persist: 'always',
        tool_name: 'access_browser_origin',
        tool_title: 'Access browser origin',
        tool_params: { origin },
        tool_params_display: [],
        origin,
      } : otherEmpty ? {
        codex_approval_kind: 'mcp_tool_call',
        connector_id: 'browser-use',
        connector_name: 'Browser use',
        persist: 'always',
        subtitle: 'ChatGPT can use records of pages visited, including from earlier sessions, to help with this task.',
        tool_params: { source: 'fixture' },
        sensitive_data: 'browsing_history',
      } : native ? {
        codex_approval_kind: 'mcp_tool_call',
        connector_id: 'computer-use',
        persist: args.code === 'approval-native-session-only' ? ['session'] : ['session', 'always'],
        tool_name: 'get_app_state',
        tool_params: { app: 'dev.lcu.NativeFixture.generated' },
      } : {},
      requestedSchema: { type: 'object', properties: form ? { secret: { type: 'string' } } : {} },
    });
    return { content: [{ type: 'text', text: native || piOrigin ? JSON.stringify(decision) : decision.action }] };
  }
  if (name === 'js' && args?.code === 'audio') {
    return { content: [{ type: 'audio', data: 'AAAA', mimeType: 'audio/wav' }] };
  }
  return { content: [{ type: 'text', text: name === 'js' ? String(args?.code) : name }] };
});
await server.connect(new StdioServerTransport());
