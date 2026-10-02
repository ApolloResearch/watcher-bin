/** Run the real Portkey server with mandatory, server-owned Watcher hooks.
 *
 * Install the pinned Portkey source and its dependencies first. This launcher
 * imports its unmodified Hono application; clients use ordinary Chat Completions.
 * The loopback listener exposes one route, validates client authentication, and
 * replaces all client Portkey routing/configuration headers before dispatch.
 */
import { randomUUID, timingSafeEqual } from 'node:crypto';
import { createRequire } from 'node:module';
import { join, resolve } from 'node:path';
import { pathToFileURL } from 'node:url';

function setting(name) {
  const value = process.env[name];
  if (!value) throw new Error(`Missing ${name}`);
  return value;
}
const source = resolve(setting('PORTKEY_SOURCE'));
const require = createRequire(join(source, 'package.json'));
const { serve } = require('@hono/node-server');
const app = (await import(pathToFileURL(join(source, 'src/index.ts')).href)).default;
const clientKey = Buffer.from(`Bearer ${setting('GATEWAY_API_KEY')}`);
const bridge = new URL(setting('WATCHER_BRIDGE_URL'));
const bridgeToken = setting('WATCHER_BRIDGE_TOKEN');
if (!['http:', 'https:'].includes(bridge.protocol) || bridge.username || bridge.password || bridge.search || bridge.hash) {
  throw new Error('Invalid WATCHER_BRIDGE_URL');
}

function hook(stage) {
  return {
    id: `watcher-${stage}`,
    type: 'guardrail',
    deny: true,
    async: false,
    checks: [{ id: 'default.webhook', parameters: {
      webhookURL: new URL(stage === 'request' ? '/validate' : '/evaluate', bridge).href,
      headers: { Authorization: `Bearer ${bridgeToken}` },
      failOnError: true,
      timeout: 420000,
    } }],
  };
}
const config = {
  provider: 'openai',
  api_key: setting('PROVIDER_API_KEY'),
  custom_host: setting('PROVIDER_BASE_URL'),
  before_request_hooks: [hook('request')],
  after_request_hooks: [hook('response')],
};

serve({
  hostname: process.env.GATEWAY_HOST || '127.0.0.1',
  port: Number(process.env.GATEWAY_PORT || 8787),
  fetch: async (request) => {
    const supplied = Buffer.from(request.headers.get('authorization') || '');
    if (supplied.length !== clientKey.length || !timingSafeEqual(supplied, clientKey)) {
      return Response.json({ error: 'Gateway authentication required' }, { status: 401 });
    }
    const url = new URL(request.url);
    if (request.method !== 'POST' || url.pathname !== '/v1/chat/completions' || url.search) {
      return Response.json({ error: 'This deployment supports POST /v1/chat/completions only' }, { status: 404 });
    }
    const headers = new Headers(request.headers);
    for (const key of [...headers.keys()]) {
      if (key.startsWith('x-portkey-')) headers.delete(key);
    }
    const conversationId = `portkey:${randomUUID()}`;
    headers.set('x-portkey-metadata', JSON.stringify({
      watcher_conversation_id: conversationId, watcher_url: url.pathname,
      watcher_provider: config.provider, watcher_user_agent: request.headers.get('user-agent'),
    }));
    headers.set('x-portkey-config', JSON.stringify(config));
    headers.set('authorization', `Bearer ${config.api_key}`);
    const response = await app.fetch(new Request(request, { headers }));
    const responseHeaders = new Headers(response.headers);
    responseHeaders.set('X-Watcher-Conversation-Id', conversationId);
    return new Response(response.body, { status: response.status, headers: responseHeaders });
  },
});
