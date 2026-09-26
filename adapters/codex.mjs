import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { StdioClientTransport } from '@modelcontextprotocol/sdk/client/stdio.js';
import { Server } from '@modelcontextprotocol/sdk/server/index.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import {
  CallToolRequestSchema,
  ElicitRequestSchema,
  ListToolsRequestSchema,
  ToolListChangedNotificationSchema,
} from '@modelcontextprotocol/sdk/types.js';
import { persistAudioContent } from './audio-files.mjs';
import { pathToFileURL } from 'node:url';

const HOST_ONLY_TOOLS = new Set(['js_add_node_module_dir', 'turn_ended']);

function callTimeout(name, args) {
  const requested = Number(args?.timeout_ms);
  return name === 'js' && Number.isFinite(requested) && requested > 0
    ? Math.max(120_000, requested + 30_000)
    : 120_000;
}

function report(label, error) {
  console.error(`${label}:`, error instanceof Error ? error.message : String(error));
}

/** Relay the original Codex CUA MCP server and replace only returned audio blocks. */
export async function runCodexBridge({ command, args = [], cwd, env } = {}) {
  if (typeof command !== 'string' || !command || !Array.isArray(args) ||
      args.some(argument => typeof argument !== 'string')) {
    throw new TypeError('Codex bridge requires the original MCP command and string arguments');
  }

  const upstreamTransport = new StdioClientTransport({
    command,
    args,
    ...(cwd ? { cwd } : {}),
    env: env ?? process.env,
    stderr: 'inherit',
  });
  const upstream = new Client({ name: 'lcu-codex-relay', version: '0.1.0' }, {
    capabilities: { elicitation: { form: {}, url: {} } },
  });
  let server;
  let connected = false;
  let shutdown;

  upstream.setRequestHandler(ElicitRequestSchema, async (request, extra) => {
    try {
      return await server.elicitInput(request.params, { signal: extra.signal });
    } catch {
      return { action: 'cancel' };
    }
  });

  try {
    await upstream.connect(upstreamTransport);
    connected = true;
    const originalCapabilities = upstream.getServerCapabilities() ?? {};
    if (!originalCapabilities.tools) {
      throw new Error('Original CUA server does not advertise tools');
    }
    const capabilities = {
      tools: originalCapabilities.tools.listChanged ? { listChanged: true } : {},
    };
    const serverOptions = { capabilities };
    const instructions = upstream.getInstructions();
    if (instructions !== undefined) serverOptions.instructions = instructions;
    server = new Server(upstream.getServerVersion() ?? { name: 'lcu-codex-relay', version: '0.1.0' }, serverOptions);
    server.onerror = error => report('Codex MCP relay server error', error);
    upstream.onerror = error => report('Codex MCP relay upstream error', error);

    server.setRequestHandler(ListToolsRequestSchema, async (request, extra) => {
      const listed = await upstream.listTools(request.params, { signal: extra.signal });
      return { ...listed, tools: listed.tools.filter(tool => !HOST_ONLY_TOOLS.has(tool.name)) };
    });

    server.setRequestHandler(CallToolRequestSchema, async (request, extra) => {
      const { params } = request;
      const progressToken = extra._meta?.progressToken;
      const options = {
        signal: extra.signal,
        timeout: callTimeout(params.name, params.arguments),
      };
      if (progressToken !== undefined) {
        options.onprogress = progress => {
          void extra.sendNotification({
            method: 'notifications/progress',
            params: { ...progress, progressToken },
          }).catch(error => report('Codex MCP progress relay error', error));
        };
      }
      const result = await upstream.callTool(params, undefined, options);
      return persistAudioContent(result);
    });

    if (originalCapabilities.tools.listChanged) {
      upstream.setNotificationHandler(ToolListChangedNotificationSchema, async notification => {
        await server.notification(notification);
      });
    }

    const closeUpstream = () => {
      if (shutdown) return shutdown;
      shutdown = (async () => {
        if (connected) {
          connected = false;
          try {
            await upstream.close();
          } catch (error) {
            report('Codex MCP upstream close failed', error);
          }
        }
      })();
      return shutdown;
    };
    server.onclose = () => { void closeUpstream(); };
    let serverClose;
    upstream.onclose = () => {
      if (server && server.transport) {
        if (!serverClose) serverClose = server.close().catch(error => {
          report('Codex MCP relay close failed', error);
        });
      }
    };
    const closeDownstream = () => {
      if (!serverClose) serverClose = server.close().catch(error => {
        report('Codex MCP relay close failed', error);
      });
      return serverClose;
    };
    const transport = new StdioServerTransport();
    await server.connect(transport);
    // The SDK stdio server does not report stdin EOF through onclose.
    process.stdin.once('end', closeDownstream);
    return {
      server,
      upstream,
      close: async () => {
        process.stdin.off('end', closeDownstream);
        await closeDownstream();
        await closeUpstream();
      },
    };
  } catch (error) {
    if (connected) await upstream.close().catch(() => {});
    throw error;
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const [command, ...args] = process.argv.slice(2);
  runCodexBridge({ command, args }).catch(error => {
    report('Codex MCP relay failed', error);
    process.exitCode = 1;
  });
}
