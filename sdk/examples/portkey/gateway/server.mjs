/** Run the real Portkey server with mandatory, server-owned Watcher hooks.
 *
 * Install the pinned Portkey source and its dependencies first. This launcher
 * imports its unmodified Hono application; clients use ordinary Chat Completions.
 * The loopback listener exposes one route, validates client authentication, and
 * replaces all client Portkey routing/configuration headers before dispatch.
 *
 * The Watcher bridge generates alternatives to refused proposals by calling
 * this same route with an `X-Watcher-Alternative` marker: an expiry, a random
 * nonce and an HMAC-SHA256 over both and the SHA-256 of the exact request body,
 * keyed from WATCHER_BRIDGE_TOKEN. Portkey's webhooks see neither request headers
 * nor the exact body bytes, so the marker is verified here: a valid marker is
 * accepted once, removed, and the request is dispatched with the provider
 * configuration only (the bridge grades the alternative itself); any other
 * request carrying the header is refused with 403.
 */
import { createHash, createHmac, randomUUID, timingSafeEqual } from 'node:crypto';
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

const ALTERNATIVE_HEADER = 'x-watcher-alternative';
// Must match _KEY_LABEL in watcher_portkey/alternatives.py, which signs markers.
const markerKey = createHmac('sha256', bridgeToken).update('watcher-portkey alternative marker v1').digest();
// `<expiry>.<nonce>.<mac>`: Unix seconds without leading zeros, a 16-byte nonce
// and an HMAC-SHA256, both lowercase hex of fixed length. Only this canonical
// form is accepted, so each marker has one spelling and the spent set below
// can key on the whole string; anything else is rejected before any arithmetic.
const MARKER = /^([1-9][0-9]{0,11})\.([0-9a-f]{32})\.([0-9a-f]{64})$/;
// Markers are minted with the bridge's remaining deadline, so a longer expiry
// is not the bridge's; the bound also caps how long a spent marker is remembered.
const MAX_MARKER_SECONDS = 600;
const MAX_ALTERNATIVE_BODY = 8 * 1024 * 1024;
// Spent markers and their expiries: each marker authorizes one request.
const spentMarkers = new Map();

/** True when `marker` was signed for exactly `body`, is unexpired and has not been used before. */
function acceptMarker(marker, body) {
  const match = MARKER.exec(marker);
  const now = Date.now() / 1000;
  if (!match) return false;
  const expiry = Number(match[1]);
  if (expiry < now || expiry > now + MAX_MARKER_SECONDS) return false;
  const digest = createHash('sha256').update(body).digest();
  const signed = Buffer.concat([Buffer.from(`${expiry}.${match[2]}.`), digest]);
  const expected = createHmac('sha256', markerKey).update(signed).digest();
  if (!timingSafeEqual(expected, Buffer.from(match[3], 'hex'))) return false;
  for (const [spent, until] of spentMarkers) {
    if (until < now) spentMarkers.delete(spent);
  }
  if (spentMarkers.has(marker)) return false;
  spentMarkers.set(marker, expiry);
  return true;
}

// The bridge marks a refusal it cannot deliver as notices, because the client
// asked for JSON content, with this value in its webhook reply's `data`
// (STRUCTURED_OUTPUT_DENIAL in watcher_portkey/bridge.py). Portkey copies that
// reply into the hook results of its 446 body; only the bridge writes there.
const STRUCTURED_OUTPUT_ERROR = {
  error: {
    message: 'Watcher refused a tool call in this response, and its notice cannot be delivered inside the requested structured output format',
    type: 'watcher_withheld',
    code: 403,
  },
};

/** Whether a Portkey hook-denied body carries the bridge's structured-output refusal. */
function structuredOutputRefusal(text) {
  try {
    const hooks = JSON.parse(text)?.hook_results?.after_request_hooks;
    return Array.isArray(hooks) && hooks.some((hook) => Array.isArray(hook?.checks) && hook.checks.some(
      (check) => check?.data?.responseData?.watcher_withheld === 'structured_output',
    ));
  } catch {
    return false;
  }
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
      // Above the bridge's 280-second deadline for a decision and its
      // alternatives, and below the 300 seconds Node's fetch waits for headers.
      timeout: 290000,
    } }],
  };
}
const provider = {
  provider: 'openai',
  api_key: setting('PROVIDER_API_KEY'),
  custom_host: setting('PROVIDER_BASE_URL'),
};
const config = {
  ...provider,
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
    const marker = headers.get(ALTERNATIVE_HEADER);
    if (marker !== null) {
      headers.delete(ALTERNATIVE_HEADER);
      const length = Number(request.headers.get('content-length'));
      const body = Number.isSafeInteger(length) && length > 0 && length <= MAX_ALTERNATIVE_BODY
        ? Buffer.from(await request.arrayBuffer())
        : null;
      if (body === null || body.length !== length || !acceptMarker(marker, body)) {
        return Response.json({ error: 'Invalid Watcher alternative marker' }, { status: 403 });
      }
      headers.set('x-portkey-config', JSON.stringify(provider));
      headers.set('authorization', `Bearer ${provider.api_key}`);
      return app.fetch(new Request(request.url, { method: 'POST', headers, body }));
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
    if (response.status === 446) {
      const text = await response.text();
      responseHeaders.delete('content-length');
      if (structuredOutputRefusal(text)) {
        return Response.json(STRUCTURED_OUTPUT_ERROR, {
          status: 403,
          headers: { 'X-Watcher-Conversation-Id': conversationId },
        });
      }
      return new Response(text, { status: 446, headers: responseHeaders });
    }
    return new Response(response.body, { status: response.status, headers: responseHeaders });
  },
});
