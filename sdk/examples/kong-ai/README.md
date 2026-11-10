# Watcher in Kong AI Proxy

Install the native `watcher` plugin on a Kong AI Proxy route to monitor every
client using that route. The plugin holds a complete model response while a
private Python bridge sends the original provider request and response through
the public Watcher SDK. Watcher converts the exchange and selects its tool calls. Clients use their existing
Chat Completions API and do not import Watcher.

The same integration follows the administrator's Watcher settings. Enforce mode
withholds denied or escalated tool calls and keeps the agent working: the model
is told why and asked for another approach, or, after an escalation, to ask the
user. Observe mode records and grades
calls without withholding them. Paused mode submits transcripts without hook
grading; separately configured trailing review can still review those sessions.
The plugin never changes the client's own tool permissions.

This is an example integration, not an officially supported Kong plugin.

## Install

Use Kong 3.9.3, Python 3.12 or newer, and a Watcher credential with
`sessions:ingest` permission. Keep the bridge on a private service network.

From this directory:

```sh
uv sync --python 3.12
docker build -t kong-with-watcher gateway
```

The development environment uses the adjacent Watcher SDK source directory.
For release-wheel installation, follow the [shared setup guide](../README.md).
The bridge can also be packaged with `uv build --wheel`.

Configure the bridge and start it:

```sh
export WATCHER_BASE_URL='https://your-watcher-server/api'
export WATCHER_API_KEY='your-watcher-api-key'
export WATCHER_BRIDGE_TOKEN='a-long-random-private-secret'
uv run watcher-kong-bridge serve --host 127.0.0.1 --port 8765 \
  --gateway-url http://127.0.0.1:8000
```

Use the public API base URL, including `/api` for Watcher Cloud or the self-hosted
Analyzer hostname. A direct local API listener can have a different prefix.

`--gateway-url` is the base URL at which the bridge reaches Kong's proxy
listener. After a refusal the bridge asks the model for an alternative by
sending a request back through the same Kong route (see
[Enforcement and limits](#enforcement-and-limits)). `--deadline-seconds`
(default 300) bounds the decision plus every alternative for one client
request; keep it below the plugin's `timeout_ms` (default 420000, 7 minutes).
Clients must allow responses that take this long.

The bridge checks ingestion permission at startup. It does not expose Watcher
credentials to clients. Use TLS when the bridge crosses a network trust boundary;
the Lua plugin verifies the bridge's certificate.

Copy `gateway/kong.yaml` to your deployment configuration and replace its provider
URL, model, provider key, bridge token and gateway client key. Set `bridge_url` to
an address Kong can reach; `127.0.0.1` means Kong's own network namespace. Keep
Kong's Admin API private and apply the plugin to every AI route you expose.
The plugin's `credential_header` (default `apikey`) must name the header your
clients authenticate with, as in key-auth's `key_names`; the bridge forwards
that credential on the alternative requests it sends for the same client.

The supplied configuration uses Kong's native `ai-proxy` and `key-auth` plugins.
Start the custom image with `KONG_DATABASE=off`, `KONG_DECLARATIVE_CONFIG` pointing
to your mounted configuration, and `KONG_PLUGINS=bundled,watcher`. The supplied
`ai-proxy.max_request_body_size` and Watcher plugin `max_body_bytes` both allow
bounded reads up to 8 MiB, including requests Kong spools to disk. Keep these
limits aligned when changing them; Kong's default AI Proxy limit is 8 KiB.
The bridge also limits its complete request/response envelope to 8 MiB, so JSON
encoding overhead and the model response count toward that shared limit.
Size response buffers for your deployment and keep Kong's request-size limit at
least as large as the accepted request. Do not expose an alternative route that
bypasses these plugins.

### Linux local demonstration

Copy `gateway/kong.yaml` to `kong.local.yaml` and replace its placeholders. Keep
`bridge_url` at `http://127.0.0.1:8765` and use the same private bridge token.
Ensure Kong's container user can read the mounted file.

With the bridge running on the Linux host, start Kong in another terminal:

```sh
docker run --rm --name watcher-kong-demo --network host \
  --env KONG_DATABASE=off \
  --env KONG_DECLARATIVE_CONFIG=/etc/kong/kong.yaml \
  --env KONG_PLUGINS=bundled,watcher \
  --env KONG_ADMIN_LISTEN=off \
  --env KONG_ADMIN_GUI_LISTEN=off \
  --env KONG_STATUS_LISTEN=off \
  --env KONG_PROXY_LISTEN=127.0.0.1:8000 \
  --mount "type=bind,source=$PWD/kong.local.yaml,target=/etc/kong/kong.yaml,readonly" \
  kong-with-watcher
```

This Linux demo shares the host network namespace, so Kong reaches the host's
loopback bridge. Its proxy listens only on host loopback. Port 8000 must be free;
if a direct local Watcher API uses it, choose another proxy port and update the
client URL below. Container deployments with separate network namespaces need a
private bridge address reachable from Kong.

## Use the route

An ordinary OpenAI client can call `/v1/chat/completions`. Supply the configured
gateway key in its `apikey` header. The gateway owns its provider credentials and
Watcher configuration; the client cannot disable the plugin with a header.

```sh
export GATEWAY_BASE_URL='http://localhost:8000/v1'
export GATEWAY_API_KEY='your-gateway-client-key'
export PROVIDER_MODEL='your-configured-model'
uv run python demo/client.py
```

The `X-Watcher-Conversation-Id` response header identifies the submitted exchange
with an ID of the form `kong:<UUID>`.
Generic clients can use that value to find their transcript in Watcher. A successful hook response
acknowledges submission; recording happens afterward and can fail. Verify the
stored transcript through Watcher's query API or Analyzer before relying on the
deployment for audit coverage.

Each exchange gets a new gateway-generated identifier. For ordinary generic
Chat Completions clients, each exchange creates a separate Watcher session that
contains the supplied full-history snapshot. Tool decisions stay with the
exchange where they were graded. Identical prompts do not join unrelated
clients' sessions just because they share a gateway key.

For harnesses using this supported Chat Completions route, Watcher may additionally
recognize a native session ID from the original request and User-Agent and group
those exchanges. The client supplies those harness cues and native IDs. Clients
that present the same recognized native session ID can be recorded together,
despite receiving different gateway IDs; these IDs do not authenticate clients.
This does not cover Messages or Responses API traffic, which this route rejects.
Each request must include its complete visible history. A client-supplied
`X-Watcher-Conversation-Id` header is ignored.

For grouped harness conversations, use the recognized native ID for a stable
lookup, such as `openai-codex=<thread-id>` for Codex. The stored gateway ID can
change on each exchange, so an earlier response header may no longer find the
session.

The bridge refuses identifiers without the `kong:` prefix. The prefix makes
the Analyzer show these sessions with the Gateway source; use the
`watcher-gateway` session source filter for these gateway captures.
Legacy captures with an `api_capture` metadata object but no `transport` field
retain the `tailscale-aperture` source label. That legacy label does not identify
which gateway supplied the capture.

## Enforcement and limits

Kong waits for every tool decision before releasing the response. A consistent
`allow` in enforce mode, or a valid `deferred` result in observe or paused mode,
preserves ordinary client behavior. Malformed or contradictory decisions withhold
delivery with HTTP 403. A valid `allow` from the administrator's grading-failure
policy still releases the response.

Every request the provider receives carries a fixed system message, added after
the client's own leading system and developer messages. It tells the model that
Watcher checks its tool calls and that `WATCHER NOTICE` and `WATCHER ESCALATION`
text in its earlier replies was written by Watcher. The text is identical on
every request, so it does not break prompt caching, and a request that already
carries it is left unchanged. Watcher receives the same request.

A `deny` or `escalate` withholds every tool call in that response, since calls
in one response often depend on each other. Instead of an error, the client
receives HTTP 200 with one completion:

- After a denial, the model is shown the refused calls with Watcher's reasons
  as tool results and asked to continue another way. Each alternative is graded
  before any of it is released. An approved alternative is delivered after the
  original text and a notice naming each refused call, with the alternative's
  own tool calls. At most three proposals are made per client request: the
  original and two alternatives. A call repeating a refused one, under any call
  ID, is refused again without being graded.
- After an escalation, or a third refused proposal, the model makes one final
  generation with `tool_choice: "none"` and is asked to stop and ask the user,
  with labelled options. Its text is delivered after the notices. If it proposes
  tool calls anyway, they are withheld without being graded and a closing notice
  asks the user how to proceed. The same notice ends a final reply that asks the
  user nothing (empty, cut off by the token limit or the provider's content
  filter, or with no question mark), and follows a sentence saying why when the
  final generation fails outright. A complete final reply that already asks a
  question is delivered unchanged. The model offers "allow this call" only when
  Watcher's grader escalated the call (decision source `policy_gateway` or
  `triage`). An escalation from a rule, a threshold or the grading-failure policy
  cannot be approved in the conversation, so the options are to skip it, do
  something else, or ask an administrator.

A refusal in a request whose `response_format` is `json_object` or
`json_schema` cannot carry a text notice, so it returns HTTP 403 with
`{"error": {"message": "Watcher refused a tool call in this response, and its notice cannot be delivered inside the requested structured output format", "type": "watcher_withheld", "code": 403}}`
and no alternative is requested; `text` or no `response_format` behaves as above.

So one client request makes at most four model calls, and only the first three
can release tool calls. The original response's ID, model and usage are kept;
usage covers the first model call only.

Alternatives are generated by requests the bridge sends back through the same
Kong route, with the client's own credential, so Kong's routing, consumer
identity, provider credentials and other plugins apply to them as they do to the
client. To reach the same route when several share a path, these requests carry
the client's original `Host` header and the client's values for the header names
the matched route requires (its `headers` predicates, at most 16); no other
client header is forwarded. A `Content-Type` predicate naming JSON is sent as the
client sent it. If a predicate cannot be sent (for example a non-JSON
`Content-Type` or the credential header), ordinary decisions and delivery are
unaffected, but a refusal ends with the notice, "No alternative was
delivered because the gateway cannot send an alternative to the client's route."
and the same fixed question asking the user how to proceed.
Routes selected by anything else, such as SNI or
source address, are not distinguished: give each such route its own path.
Each carries an `X-Watcher-Alternative` header: an expiry and an
HMAC-SHA256 over the expiry and the exact request body, keyed from the bridge's
Watcher API key. On such a request the plugin asks the bridge to verify the
header, then passes the exchange through without the system notice or grading
(the bridge grades the alternative itself) and removes the header before the
request goes upstream. A missing, malformed, expired or forged header, or one
signed for a different body, returns HTTP 403. Each alternative is graded in the
client request's own Watcher session, under the same `kong:` ID. Its history
repeats the refused calls with the gateway's refusal receipts as their results;
because Watcher already holds a decision for each of those calls, it does not
record them as calls that ran. Every Watcher request declares that the gateway
withholds refused calls (`withholds_refused_calls`), so an enforced refusal is
recorded as blocked rather than waiting for an answer. After Kong has the reply,
the bridge records the delivered completion in the same session, naming every
call it withheld (`withheld_tool_use_ids`: refused calls and their siblings,
never a delivered call), so the Analyzer can show them before that reply. That
recording never delays or changes the client's response; a failure is only
logged. A Watcher server older than these fields rejects them, and the bridge
then sends the same request once more without them, leaving refusals pending.
The final generation is not graded; its calls are withheld unevaluated and are
not named, since Watcher never saw them. Watcher stores exchanges
asynchronously; if it stores an alternative before the original proposal, an
allowed call withheld with the refused one can still end up recorded as
completed. A refused call is recorded as blocked either way.

If an alternative cannot be obtained or graded (a provider or Kong failure, a
response the bridge cannot verify, a Watcher error, or the deadline), nothing
from that attempt reaches the client. The response ends with the notices so far,
a sentence saying why no alternative was delivered and a fixed question asking
the user how to proceed, so the agent's turn never ends on a notice alone.

This gateway example has no approval screen or mechanism to resume an escalated
call: the user answers in the conversation, and Watcher grades the call again
when the model proposes it.

The route accepts buffered OpenAI Chat Completions and client function tools.
Streaming, multiple choices, hidden provider history and other API routes
are rejected. Requests carrying an `Upgrade` header return HTTP 400 before the
plugin contacts the bridge or provider. The response gate requires buffered HTTP,
so WebSockets and other protocol upgrades are unsupported. Keep the
`ai-proxy` and `key-auth` plugins in the supplied deployment configuration.
Watcher handles provider message conversion; local verification
covers textual conversations. Other content types require verification against
your server and provider. Original JSON text preserves native IDs and argument
types across the Lua bridge. Incomplete responses are withheld.

The bridge independently inventories the response's tool paths and native IDs.
Every delivered proposal needs a matching allowed or deferred decision, including
calls the backend converter might omit as superseded context.

The plugin can stop tool calls before a client receives them. It cannot stop
tools that already ran at the provider, prove that a client executed a released
tool, or capture results the client never sends in a later request. It does not
monitor unrelated Kong routes or direct calls that bypass Kong.

Permanent Watcher request rejections of the client's response, such as an
unconvertible exchange, withhold it with HTTP 403. Connection errors, timeouts,
rate limits and server failures return HTTP 503. A decision produced by an
administrator's grading-error policy follows that policy. Tool-call IDs must be
unique across the full conversation; reusing an earlier ID for a new call is
rejected. The bridge has no durable delivery queue or automatic replay.

## Tests and packaging

`src/watcher_kong_ai/bridge.py` is the bridge's HTTP endpoint and
`exchange.py` the SDK boundary; `alternatives.py` and `notices.py` build the
replacement response after a refusal. `gateway/` contains the
native plugin and deployment configuration. `tests/` covers conversion,
decision handling and recovery after refusals; `tests/native/` exercises
installed Kong with local fixtures.
`metadata.yaml` records verified versions and test scope.

```sh
env -i PATH="$PATH" ../run-without-network.sh "$PWD/.venv/bin/python" \
  -m pytest --noconftest -c pyproject.toml tests
```

Install dependencies before entering the isolated test environment. Synthetic
model and grading responses exercise mechanics, not model quality or hosted
service availability.

Run the installed Kong plugin with local model and Watcher protocol fixtures:

```sh
bash tests/native/run.sh
```

The recipe builds the SDK and example wheels, then starts Kong and the bridge in
one network-isolated namespace. It retains installed-artifact checks, raw
requests, JUnit results and container identities under the printed artifact path.
The Watcher replies in this recipe are fixtures; actual-backend verification is a
separate test scope reported in metadata.
