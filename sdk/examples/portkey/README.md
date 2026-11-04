# Portkey gateway

Install Watcher on a Portkey gateway so existing clients are monitored without
importing Watcher or changing their tool dispatcher. The server launcher adds
mandatory native Portkey webhooks to every request on its Chat Completions route.
The webhooks call a private Python service that uses the public Watcher SDK.

The same installation follows the Watcher organization's settings. In enforce
mode, the gateway never delivers a denied or escalated tool call. It explains
the refusal to the client in the reply and asks the model for another approach,
as described in [Refusals and alternatives](#refusals-and-alternatives).
In observe or paused mode, it releases the response and preserves the client's
normal tool permissions. It does not implement an interactive approval screen:
after an escalation, the model asks the user in its reply.

## Supported traffic

This example supports **buffered OpenAI Chat Completions**, text messages and
client-executed function tools, with one response choice.
It rejects streaming, Responses, Realtime, other routes, multimodal messages and
unsupported function formats. Provider-hosted tools may run before a response
reaches the gateway and are outside this enforcement boundary.

Each exchange receives a gateway-generated identifier of the form
`portkey:<UUID>`, returned in `X-Watcher-Conversation-Id`. For generic Chat
Completions clients, each exchange creates a separate Watcher session containing
the supplied full history; identical prompts and shared API keys do not join
those sessions. Decisions remain attached to the exchange where they were graded.

For recognized harnesses using Chat Completions, Watcher can also extract a native
session ID from the request and User-Agent and group those exchanges. The gateway
identifier does not disable this grouping. Harness markers and native session IDs
are client-supplied metadata, not authenticated user identities. The local
isolation checks cover generic clients; they do not verify isolation against
clients impersonating another harness session.

For grouped harness conversations, use the recognized native ID for a stable
lookup, such as `openai-codex=<thread-id>` for Codex. The stored gateway ID can
change on each exchange, so an earlier response header may no longer find the
session.

The bridge refuses identifiers without the `portkey:` prefix. The prefix makes
the Analyzer show these sessions with the Gateway source; use the
`watcher-gateway` session source filter for these gateway captures.
Legacy captures with an `api_capture` metadata object but no `transport` field
retain the `tailscale-aperture` source label. That legacy label does not identify
which gateway supplied the capture.

## Install

Use Python 3.12+, uv, Node.js 24 and npm. Install this example from its directory:

```sh
uv sync --python 3.12
```

Install the pinned Portkey gateway source and dependencies in a separate directory:

```sh
git clone https://github.com/Portkey-AI/gateway.git /path/to/portkey-gateway
git -C /path/to/portkey-gateway checkout 669825cbe89ee51569918b8f78a9db486fd69dd4
cd /path/to/portkey-gateway
npm ci
```

The source pin corresponds to package version 1.15.2. The launcher imports the
unmodified Portkey Hono application; it does not call a mock gateway or replace
the native hook implementation. Keep the installed gateway source available.

## Configure and start

Set server-side configuration, keeping credentials out of client code and source:

```sh
export PORTKEY_SOURCE=/path/to/portkey-gateway
export WATCHER_BASE_URL=https://your-watcher-server/api
export WATCHER_API_KEY=your-watcher-key
export WATCHER_BRIDGE_URL=http://127.0.0.1:8765
export WATCHER_BRIDGE_TOKEN=your-private-bridge-secret
export PROVIDER_BASE_URL=https://api.openai.com/v1
export PROVIDER_API_KEY=your-provider-key
export GATEWAY_API_KEY=your-client-facing-gateway-key
```

The bridge also reads `GATEWAY_API_KEY`, and `GATEWAY_HOST` and `GATEWAY_PORT`
when set, to reach the launcher when it asks the model for an alternative.

Start the bridge from this example directory:

```sh
.venv/bin/python -m watcher_portkey.bridge serve --port 8765
```

In another terminal with the same environment, start the gateway:

```sh
node --import "$PORTKEY_SOURCE/node_modules/tsx/dist/loader.mjs" gateway/server.mjs
```

The default listener is `127.0.0.1:8787`. An ordinary OpenAI-compatible client uses
`http://127.0.0.1:8787/v1` and `GATEWAY_API_KEY`. `GATEWAY_HOST` and `GATEWAY_PORT`
configure the listener. Keep the SDK bridge private; expose the gateway through
your normal authenticated TLS deployment.

The launcher validates client authentication, replaces all caller-supplied
`x-portkey-*` headers, and installs both request and response checks. Calling a
separate unconfigured Portkey process bypasses these checks: expose only this
launcher to monitored clients. `deny: true` and `failOnError: true` are mandatory
because Portkey otherwise permits some failed webhook checks.

For a plain client demonstration, set `GATEWAY_URL=http://127.0.0.1:8787/v1` and
`PROVIDER_MODEL`, then run `.venv/bin/python demo/client.py`. The client imports
httpx, not Watcher.

## Decisions and recording

A response is released only when every client-visible tool proposal has an
applied allow or deferred result for its unique native tool-call ID.
A skipped or missing result withholds the whole response, even when Watcher
returned an empty list. Text-only responses are also submitted for ingestion.

The bridge sends the original request and completed response bodies, real client
User-Agent, endpoint path and provider to `pre_tool_use_hook`. Watcher converts
the transcript on the backend; no settings override is sent. It uses the
applied decision: `allow` and `deferred` release the native response; `deny`
and `escalate` withhold every call in it and start the recovery described
below; missing results and mismatched call IDs withhold the whole response.
A configured grading-failure allow is respected as server policy. A bridge or
Watcher transport failure also withholds the response, including in observe mode.

A refused response is answered with HTTP 200, as described below. When no
decision can be verified (a bridge or Watcher failure, or outcomes that do not
match the response's calls), Portkey returns its hook-denied HTTP 446 error and
no executable tool call reaches the client. The callback cannot stop a tool a
client runs independently of gateway output. Unsupported streaming is rejected
before the provider call because the pinned Portkey response-hook path cannot
enforce its post-response verdict on a stream.

### Refusals and alternatives

Coding agents end their turn on a text-only reply or an error, so a bare refusal
stops the task. Instead, the bridge keeps the client's request open and works
with the model inside it:

- **Every request** gets a fixed system message after the client's leading
  system and developer messages. It tells the model that `WATCHER NOTICE` and
  `WATCHER ESCALATION` text in its earlier replies was written by Watcher and is
  genuine. The text never changes, so prompt caching is unaffected, and a
  request that already carries it is left unchanged. Watcher receives the same
  request the provider does.
- **After a denial**, the response's calls are withheld together. The bridge
  sends the model its proposal with one tool result per call, giving Watcher's
  reason and inviting another approach, and generates an alternative. The
  alternative is graded in the client's own Watcher session, under the same
  `portkey:` conversation ID. Watcher already holds a decision for every call
  of the refused proposal, so those calls are not recorded again as calls
  that ran. An allowed alternative is delivered in one reply: the original
  text, a notice per refused call, and the alternative's text and calls. A
  call that repeats a refused operation under a new ID is refused again
  without grading. Watcher never saw that proposal, so it and its refusal are
  left out of the history Watcher grades later alternatives with, though the
  model still sees them.
- **After an escalation, or a third refused proposal**, one last generation is
  made with `tool_choice` set to `none` (when the request offers tools). The
  model is asked to stop and ask the user, with labelled options. Allowing the
  call is offered only when Watcher's graders made the decision; a rule,
  threshold or grading-failure escalation cannot be approved in the
  conversation. If that generation proposes calls anyway, they are withheld
  without being sent to Watcher, and a closing notice puts the question to the
  user. The same notice closes a final reply that asks the user nothing: one
  with no text, one cut off by the token limit or the provider's content
  filter, or one with no question mark. A complete final reply that already
  asks a question is delivered unchanged. Calls in a final reply are dropped
  without being parsed, so a reply cut off mid-call keeps its text.
- **When the client asked for JSON content** (`response_format` of type
  `json_object` or `json_schema`), a notice would make that JSON unparseable.
  A refusal is answered instead with HTTP 403 and the error type
  `watcher_withheld`, and no alternative is generated; Watcher still records
  the refusal.
- **If generating or grading an alternative fails** or the time limit is
  reached, no call from that attempt is delivered. The reply ends with the
  notices so far, a sentence saying why no alternative followed and a fixed
  question asking the user how to proceed, so the agent's turn never ends on a
  notice alone. If the final generation fails, the sentence says why no final
  reply followed and the closing notice still asks the user how to proceed.

Every exchange the bridge sends Watcher declares that refused calls are
withheld (`withholds_refused_calls`), so Watcher records an enforced denial or
escalation as blocked rather than awaiting an answer. After a refusal, the
bridge records the reply it delivered once that reply has been returned, in
the background so it never delays or fails delivery. That recording names
every call withheld in the reply's favour (`withheld_tool_use_ids`): each call
of each refused proposal, except a call the reply delivers. The reply's own
calls were graded with their alternative, so they are recorded as history and
not graded again. A Watcher server older than this example rejects both
fields; the bridge then sends the exchange again without them and logs a
warning, so it is still evaluated and recorded, as before.

Watcher stores each exchange after answering it. If it stores an
alternative's exchange before the original proposal's, a call withheld only
because a sibling was refused (one Watcher itself allowed) is first seen in
that history with the gateway's receipt and recorded as completed, and the
original decision arriving later keeps that status. A refused call is not
affected: the declaration that refused calls are withheld lets its blocked
status replace such a record.

A client request makes at most four model calls; only the first three can
deliver tool calls. The original decision, the alternatives and the final
generation share one 280-second deadline. It stays below the launcher's
290-second webhook timeout and the 300 seconds Node's built-in fetch waits for
response headers.

Alternatives are generated through the launcher itself, so they use the same
Portkey route and provider configuration as the client's request. The bridge
authenticates with `GATEWAY_API_KEY`; the launcher accepts only that one shared
key, so this is the client's own credential. Portkey's webhooks receive neither
request headers nor the exact request bytes, so the launcher checks these
requests itself. Each carries an `X-Watcher-Alternative` header: an expiry, a
random nonce and an HMAC-SHA256 over both and the SHA-256 of the exact body,
keyed from `WATCHER_BRIDGE_TOKEN`. The launcher accepts each marker once, for that body,
before it expires. It removes the header and dispatches the request with the
provider configuration only, so the alternative is not graded twice and does
not start another recovery. Any other request carrying the header is refused
with HTTP 403.

Portkey adds a `hook_results` object to every reply that passed through the
webhooks, including the bridge URL. OpenAI-compatible clients ignore the extra
field.

Tool results and final assistant replies are recorded when included in subsequent
full-history requests. For generic clients, these are separate sessions and the
later snapshots do not copy prior stored judgments.
Watcher schedules ingestion after the hook reply; a successful reply is not a
storage receipt. Use the returned conversation ID to inspect the matching
snapshot in Watcher. The SDK key needs session ingestion permission as well as
permission to monitor.

## Verify locally

For a complete installed-artifact test, use Python 3.12, uv and Docker, then run:

```sh
tests/native/run.sh
```

The recipe downloads checksum-pinned gateway and toolchain archives, builds the
SDK and example wheels, and checks their installed bytes before running tests.
It runs the actual gateway with local provider and Watcher protocol fixtures in
a container with external networking disabled. The protocol checks include the
system notice reaching the provider, a denial answered with an alternative
generated through the gateway, the escalation and three-refusal final replies,
and the alternative marker: forged, expired, wrong-body, replayed and
unauthenticated requests are refused, and an accepted one is not graded again. Reports include JUnit results,
runtime versions, source hashes and the native executable/plugin identities.
Dependency downloads happen during the build; the test phase is isolated.

Run the bridge's contract tests without network access:

```sh
../run-without-network.sh .venv/bin/python -m pytest --noconftest -c pyproject.toml tests/
```

The complete recipe starts the real Portkey process, a local provider and the
SDK bridge. It verifies the Node binary and installed launcher against their
build receipt before sending model traffic.

Install dependencies before isolating the runtime. This protocol probe does not
prove Watcher storage. The separate backend test driver supplies a real local
Watcher relay and reads the stored transcript and decisions through the public
SDK. `metadata.yaml` states which runs have been completed.

The bridge checks the public permission endpoint at startup and refuses to start
without `sessions:ingest`. It does not require session-read permission to run.

Buffered text-only replies stopped by an output limit or content filter are
submitted and delivered unchanged. Incomplete responses containing tool proposals
are withheld in every mode; the integration never executes a partial proposal.
