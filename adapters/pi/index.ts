import { randomUUID } from 'node:crypto';
import { userInfo } from 'node:os';
import { fileURLToPath } from 'node:url';
import type { ExtensionAPI, ExtensionContext } from '@earendil-works/pi-coding-agent';
import type { TSchema } from 'typebox';
import { createCuaClient, nativeAppApprovalOptions, nativeAppApprovalResponse } from '../client.mjs';
import { persistAudioContent } from '../audio-files.mjs';

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

export default function (pi: ExtensionAPI, options: {
  command?: string[];
  connectOnLoad?: boolean;
  ompEssentialTools?: boolean;
} = {}) {
  let bridge: ReturnType<typeof createCuaClient> | undefined;
  let pending: Promise<ReturnType<typeof createCuaClient>> | undefined;
  let active: { sessionId: string; turnId: string } | undefined;
  let pendingCleanup: { turn: { sessionId: string; turnId: string }; event: 'Stop' | 'Interrupt' } | undefined;
  let cleanupInFlight: Promise<void> | undefined;
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
        ...(options.ompEssentialTools ? { loadMode: 'essential' } : {}),
        async execute(id, args, signal, _onUpdate, ctx) {
          const current = await connected();
          if (!active) throw new Error('LCU requires an active Pi agent turn');
          approvalContext = ctx;
          const result = await current.call(name, args, {
            ...active, toolCallId: id, model: ctx.model?.id, signal,
          });
          return piContent(await persistAudioContent(result));
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
            const nativeApproval = nativeAppApprovalOptions(params);
            if (nativeApproval) {
              if (typeof ctx.ui.select !== 'function') return { action: 'cancel' as const };
              const selectedLabel = await ctx.ui.select(nativeApproval.message,
                nativeApproval.choices.map(choice => choice.label));
              const selectedValue = nativeApproval.choices.find(choice => choice.label === selectedLabel)?.value ?? 'cancel';
              return nativeAppApprovalResponse(params, selectedValue);
            }
            const schema = params?.requestedSchema;
            if (params?.mode === 'url' || schema?.type !== 'object' ||
                Object.keys(schema.properties ?? {}).length !== 0 ||
                (schema.required?.length ?? 0) !== 0 || typeof params.message !== 'string') {
              return { action: 'cancel' as const };
            }
            if (typeof ctx.ui.select !== 'function') return { action: 'cancel' as const };
            const selected = await ctx.ui.select(params.message, ['Allow', 'Decline']);
            if (selected === 'Allow') return { action: 'accept' as const, content: {} };
            if (selected === 'Decline') return { action: 'decline' as const };
            return { action: 'cancel' as const };
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

  async function finish(event: 'Stop' | 'Interrupt', reconnect = true) {
    if (active) pendingCleanup = { turn: active, event };
    active = undefined;
    if (cleanupInFlight) return cleanupInFlight;
    const cleanup = pendingCleanup;
    if (!cleanup) return;
    const attempt = (async () => {
      const client = bridge ?? (reconnect ? await connected() : undefined);
      if (!client) return;
      await client.turnEnded({ ...cleanup.turn, event: cleanup.event });
      if (pendingCleanup === cleanup) pendingCleanup = undefined;
    })();
    cleanupInFlight = attempt;
    try {
      await attempt;
    } finally {
      if (cleanupInFlight === attempt) cleanupInFlight = undefined;
    }
  }

  async function leaveSession() {
    try {
      await finish('Interrupt', false);
    } finally {
      await bridge?.close();
      bridge = undefined;
      approvalContext = undefined;
    }
  }

  pi.on('before_agent_start', async (event, ctx) => {
    approvalContext = ctx;
    const client = await connected();
    // OMP keeps system-prompt sections as an array. Preserve those boundaries
    // and append LCU's instructions as one additional section. Pi uses a string.
    return { systemPrompt: Array.isArray(event.systemPrompt)
      ? [...event.systemPrompt, client.instructions]
      : `${event.systemPrompt}\n\n${client.instructions}` };
  });
  pi.on('agent_start', async (_event, ctx) => {
    // A failed turn_ended must succeed before Pi starts another turn. Keep the
    // old turn's identifiers so cleanup can be retried without enabling its tools.
    await finish('Interrupt');
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

  // Connect during OMP extension loading before its first tool snapshot.
  if (options.connectOnLoad) return connected().then(() => undefined);

}
