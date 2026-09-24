import { randomUUID } from 'node:crypto';
import { userInfo } from 'node:os';
import { fileURLToPath } from 'node:url';
import type { ExtensionAPI, ExtensionContext } from '@mariozechner/pi-coding-agent';
import type { TSchema } from '@sinclair/typebox';
import { createCuaClient } from '../client.mjs';

type OriginalContent = { type: string; text?: string; data?: string; mimeType?: string };

function piContent(result: { content: OriginalContent[]; isError?: boolean }) {
  const content = result.content.map(item => {
    if (item.type === 'text' && typeof item.text === 'string') return { type: 'text' as const, text: item.text };
    if (item.type === 'image' && typeof item.data === 'string' && typeof item.mimeType === 'string') {
      return { type: 'image' as const, data: item.data, mimeType: item.mimeType };
    }
    throw new Error(`Pi cannot represent original CUA ${item.type} content`);
  });
  if (result.isError) {
    throw new Error(content.filter(item => item.type === 'text').map(item => item.text).join('\n') || 'Original CUA tool failed');
  }
  return { content, details: { originalResult: result } };
}

function commandFromEnvironment(selected?: string[]) {
  const raw = process.env.LCU_MCP_COMMAND;
  if (raw) return JSON.parse(raw);
  if (selected) return selected;
  const runtime = fileURLToPath(new URL('../../bin/lcu', import.meta.url));
  if (process.platform === 'darwin') return [runtime];
  if (process.platform === 'linux') {
    const session = fileURLToPath(new URL('../../bin/lcu-session', import.meta.url));
    return [session, '--user', userInfo().username, '--', runtime];
  }
  throw new Error(`LCU does not support ${process.platform}`);
}

function originsFromEnvironment() {
  const raw = process.env.LCU_APPROVED_ORIGINS;
  return raw ? JSON.parse(raw) : [];
}

export default function (pi: ExtensionAPI, options: { command?: string[] } = {}) {
  let bridge: ReturnType<typeof createCuaClient> | undefined;
  let pending: Promise<ReturnType<typeof createCuaClient>> | undefined;
  let active: { sessionId: string; turnId: string } | undefined;
  let approvalContext: ExtensionContext | undefined;

  function registerTools(client: ReturnType<typeof createCuaClient>) {
    // Pi refreshes tools registered during before_agent_start before its model call.
    for (const descriptor of client.publicTools()) {
      const name = descriptor.name;
      pi.registerTool({
        name,
        label: `LCU ${name}`,
        description: descriptor.description ?? '',
        parameters: descriptor.inputSchema as TSchema,
        async execute(_id, args, signal, _onUpdate, ctx) {
          const current = await connected();
          if (!active) throw new Error('LCU requires an active Pi agent turn');
          approvalContext = ctx;
          const result = await current.call(name, args, {
            ...active, model: ctx.model?.id, signal,
          });
          return piContent(result);
        },
      });
    }
  }

  async function connected() {
    if (bridge) return bridge;
    if (!pending) {
      pending = (async () => {
        const candidate = createCuaClient({
          command: commandFromEnvironment(options.command),
          cwd: process.cwd(),
          allowedOrigins: originsFromEnvironment(),
          onElicitation: async params => {
            const ctx = approvalContext;
            if (!ctx?.hasUI) return { action: 'cancel' as const };
            const schema = params?.requestedSchema;
            if (params?.mode === 'url' || schema?.type !== 'object' ||
                Object.keys(schema.properties ?? {}).length !== 0 ||
                (schema.required?.length ?? 0) !== 0 || typeof params.message !== 'string') {
              return { action: 'cancel' as const };
            }
            const approved = await ctx.ui.confirm('LCU approval', params.message);
            return { action: approved ? 'accept' as const : 'decline' as const,
              ...(approved ? { content: {} } : {}) };
          },
        });
        await candidate.connect();
        bridge = candidate;
        registerTools(candidate);
        return candidate;
      })().finally(() => { pending = undefined; });
    }
    return pending;
  }

  async function finish(event: 'Stop' | 'Interrupt') {
    const turn = active;
    active = undefined;
    if (turn && bridge) await bridge.turnEnded({ ...turn, event });
  }

  async function leaveSession() {
    try {
      await finish('Interrupt');
    } finally {
      await bridge?.close();
      bridge = undefined;
      approvalContext = undefined;
    }
  }

  pi.on('before_agent_start', async (event, ctx) => {
    approvalContext = ctx;
    const client = await connected();
    return { systemPrompt: `${event.systemPrompt}\n\n${client.instructions}` };
  });
  pi.on('agent_start', async (_event, ctx) => {
    active = { sessionId: ctx.sessionManager.getSessionId(), turnId: randomUUID() };
    approvalContext = ctx;
  });
  pi.on('agent_end', async (event, ctx) => {
    const lastAssistant = [...event.messages].reverse().find(message => message.role === 'assistant');
    const interrupted = !lastAssistant || ctx.signal?.aborted ||
      (lastAssistant?.role === 'assistant' && lastAssistant.stopReason === 'aborted');
    await finish(interrupted ? 'Interrupt' : 'Stop');
  });
  pi.on('session_shutdown', leaveSession);

}
