# Watcher in Agent Router

Attach a Watcher external processor to an
[Agent Router](https://github.com/theagentrouter/agent-router) gateway to
monitor every client using it. Agent Router, formerly Envoy AI Gateway, runs on
Envoy Gateway, and Envoy Gateway's `EnvoyExtensionPolicy` adds external
processors to a Gateway. This example's processor sends each Chat Completions
request and its response to Watcher through the public Watcher SDK, and lets a
tool call reach the client only when Watcher's decision allows it. A buffered
response is held whole until then; a streamed response delivers its text at
once and holds only the events from its first tool call on. Clients keep using
the OpenAI API and do not import Watcher.

The processor follows the administrator's Watcher settings. Enforce mode
withholds denied or escalated tool calls, explains them in the response and
can ask the model for an approved alternative within the same request. Observe mode
records and grades calls without withholding them. Paused mode submits
transcripts without hook grading. The processor never changes a client's own
tool permissions.

This is an example integration, not an officially supported Agent Router
extension.

## Install

Use Python 3.12 or newer, the `aigw` CLI from an
[Agent Router release](https://github.com/theagentrouter/agent-router/releases)
(tested with v1.1.0), and a Watcher credential with `sessions:ingest`
permission. `aigw run` supports Linux and macOS and downloads Envoy on first
use.

From this directory:

```sh
uv sync --python 3.12
```

The development environment uses the adjacent Watcher SDK source directory.
For release-wheel installation, follow the [shared setup guide](../README.md).

## Run locally

Start the processor in one terminal. It checks the credential's ingestion
permission before listening:

```sh
export WATCHER_BASE_URL='https://your-watcher-server/api'
export WATCHER_API_KEY='your-watcher-api-key'
export GATEWAY_API_KEY='a-long-random-client-key'
export GATEWAY_URL='http://127.0.0.1:1975'
uv run watcher-agent-router serve --address 127.0.0.1:50051
```

Use the public API base URL, including `/api` for Watcher Cloud or the
self-hosted Analyzer hostname.

`GATEWAY_API_KEY` is the key gateway clients must send in the `x-api-key`
header. Agent Router injects the operator's provider key into every request it
forwards, so an unauthenticated gateway would let any caller who can reach it
spend that account. The processor answers a missing or wrong key with HTTP 401
before the provider or Watcher is called, and removes the header before the
request goes upstream. It refuses to start without `GATEWAY_API_KEY` unless you
pass `--allow-unauthenticated-clients`, which is only for deployments where a
Gateway `SecurityPolicy` already authenticates clients (see below).

`GATEWAY_URL` is the gateway's own client listener. When Watcher refuses a
proposal, the processor asks the model for alternatives through it, with the
gateway key (see [Alternatives](#alternatives)). It requires `GATEWAY_API_KEY`.
Leave it unset to deliver refusals with their explanation alone; the processor
says so when it starts.

The gRPC connection from Envoy to the processor is not authenticated: keep the
processor on loopback, a Unix socket (`--address unix:/path/to.sock`) or a
private network that only Envoy can reach. Put TLS in front of the gateway
listener before exposing it beyond the local machine.

Start Agent Router with the supplied configuration in another terminal:

```sh
export OPENAI_API_KEY='your-provider-key'
aigw run gateway/agent-router.yaml
```

`aigw run` substitutes these environment variables in the configuration:

| Variable | Default | Purpose |
| --- | --- | --- |
| `OPENAI_API_KEY` | none | Provider key Agent Router injects upstream; clients never see it. |
| `OPENAI_HOST` | `api.openai.com` | Host of an OpenAI-compatible provider reached over TLS on port 443. |
| `WATCHER_PROCESSOR_ADDRESS` | `127.0.0.1` | IP address of the Watcher processor. |
| `WATCHER_PROCESSOR_PORT` | `50051` | Port of the Watcher processor. |

The gateway listens on `http://localhost:1975`. Then call it with an ordinary
OpenAI client:

```sh
export GATEWAY_BASE_URL='http://localhost:1975/v1'
export GATEWAY_API_KEY='a-long-random-client-key'
export PROVIDER_MODEL='a-model-your-provider-serves'
uv run python demo/client.py
```

The demo offers one tool and prints the released tool call, or the assistant
text explaining why Watcher withheld it. `demo/.env.example` lists every variable.

On Kubernetes, run the processor in a Pod with
`watcher-agent-router serve --address 0.0.0.0:50051`, since the default
loopback address is unreachable through a Service. Expose that port with a
Service and restrict access to Envoy, for example with a NetworkPolicy. Then
adapt a copy of the configuration for your Agent Router installation. Only
`aigw run` substitutes the `${...}` placeholders; `kubectl apply` does not. In
your copy, replace each placeholder with a literal value, change the
`watcher-processor` Backend endpoint from `ip` to `fqdn` with the processor
Service's hostname, and remove the `openai-apikey` Secret from the file so you
can create it separately in the `BackendSecurityPolicy`'s namespace (for example
`kubectl create secret generic openai-apikey --namespace default
--from-literal=apiKey=...`). Keep `WATCHER_API_KEY` and `GATEWAY_API_KEY` in
Secrets available only to the processor, and give every processor replica the
same `WATCHER_API_KEY`. Set `GATEWAY_URL` to an address of the Gateway's
listener that the processor Pod can reach, such as its in-cluster Service.
Deployments can instead authenticate clients with an Envoy
Gateway `SecurityPolicy` on the Gateway (API keys, JWT or OIDC) and start the
processor with `--allow-unauthenticated-clients`, which disables the processor's
key check even if `GATEWAY_API_KEY` is set; alternatives are then unavailable,
because the processor calls the listener with the gateway key. Under `aigw run` v1.1.0, a
`SecurityPolicy` that references a `Secret`, such as API-key authentication,
does not work: `aigw run` does not pass user-defined `Secret` resources to Envoy
Gateway, and every request then fails with HTTP 500. Policies that need no
`Secret`, such as JWT with a remote key set, were not tested with this example.

## What the configuration does

`gateway/agent-router.yaml` is the Agent Router OpenAI configuration plus two
resources:

- The `watcher-processor` Backend names the processor's gRPC address.
- The `watcher` EnvoyExtensionPolicy attaches it to the whole Gateway with
  buffered request and response bodies, a 450-second message timeout and
  `failOpen: false`. A full grade can take several minutes, so the processor
  allows each response's decision 420 seconds in total, including any
  alternatives, and answers a slower first decision with its own logged 503
  before Envoy's timeout. The 660-second route timeout is one
  deadline shared by the provider call and the decision, which leaves the
  provider about 210 seconds; the stream idle timeout is also 660 seconds.

Gateway scope covers every route on the listener, so a client cannot reach the
provider through a route without the processor. The processor answers anything
other than `POST /v1/chat/completions` with HTTP 404 (after the key check)
before the provider is
called. Agent Router answers `GET /v1/models` itself before the processor sees
the request, so the processor replaces that listing with the same 404; Agent
Router's own routing errors, such as a request without a model, pass through.
Envoy returns an HTTP 5xx error if the processor is unreachable, fails or times
out, including when the processor stops while a grade is pending; it never
releases the response in that case.

The connection buffer limit is 8 MiB, matching the processor's body limit.
Envoy answers larger requests with HTTP 413.

## Conversation IDs

Each exchange gets a new conversation ID of the form `agent-router:<UUID>`,
returned in the `X-Watcher-Conversation-Id` response header. A successful
Watcher response acknowledges submission; recording happens afterward and can
fail. Verify the stored transcript through Watcher's query API or Analyzer
before relying on the deployment for audit coverage.

For generic Chat Completions clients, each exchange creates a separate Watcher
session containing the full history the client sent. For coding harnesses that
use this route, Watcher may also recognize a native session ID from the request
and `User-Agent` and group those exchanges. Those IDs come from the client and
do not authenticate it.

The `agent-router:` prefix makes the Analyzer show these sessions with the
Gateway source. Use the `watcher-gateway` session source filter to find them.

Alternatives requested after a refusal are graded in the same session, as
described under [Alternatives](#alternatives).

## Enforcement and limits

The processor waits for every tool decision before releasing a buffered
response, or the tool-bearing part of a streamed one. An
`allow` in enforce mode, or a valid `deferred` result in observe or paused mode,
releases it unchanged. A valid `allow` from the administrator's grading-failure
policy also releases it.

### System notice

The processor adds one fixed system message to every request before the
provider sees it. It tells the model that Watcher checks each tool call, that a
`WATCHER NOTICE` or `WATCHER ESCALATION` in its own earlier replies was written
by Watcher, and how to continue after each. Without it, models often call those
notices injected text or their own mistake and retry the refused call. The
message goes after the leading system and developer messages, so the caller's
instructions keep their order and their cached prefix. It is byte-identical on
every request, so the provider's prompt cache still applies, and a request that
already contains it, for example from managed client settings, is left
unchanged. Watcher grades the request with the notice, as the provider received
it. A request too close to the 8 MiB limit to take the notice (about 1.3 KB) is
refused with HTTP 413 before the provider is called.

### Denials

When Watcher denies or escalates a call, the harness still receives an ordinary
response rather than an error. The processor removes every executable call from
that response, including calls Watcher allowed alongside the refused one, and
adds a notice to its assistant text, one paragraph per call. Each paragraph
starts `WATCHER NOTICE (added by Watcher, not written by the assistant)`, or
`WATCHER ESCALATION` for an escalation, names the call with its arguments and
gives Watcher's public explanation (`verdict.explanation`). Calls withheld only
because a sibling was refused get their own line. Long arguments and reasons
are shortened. A buffered response keeps HTTP 200; a streamed one ends with the
notice as a normal text event. The client's next request carries the notice in
the model's own turn, and the system notice tells the model it is genuine. An
unattended client therefore never executes a refused call. A request that asks for
JSON content (`response_format` of type `json_object` or `json_schema`) would
be broken by that text, so a refusal there is returned as HTTP 403 (or an SSE
error event when streaming) with `type: watcher_withheld`, and no alternative
is generated. This example has no
approval screen or way to resume an escalated call in the same request. With
`GATEWAY_URL` set, the processor also asks the model what to do next, as
described below.

### Alternatives

With `GATEWAY_URL` set, the processor asks the model for its next step within
the same client request. It copies the client's request, appends the refused
proposal and one tool result per call, and sends it to Agent Router's listener
as a buffered request (`stream: false`) with the gateway key. It therefore uses
the client's route, model, backend and provider credentials.

**After a denial**, the denied call's tool result gives Watcher's reason and
asks the model to continue the task another way, because Watcher checks every
call. The model is not invited to explain itself in text instead: an agent's
turn ends at a text-only reply, since harnesses call the model again only after
tool results. Tools, `tool_choice` and every other option are kept, so an
alternative cannot use a tool the client excluded; a forced tool choice can use
up both alternatives where the model would otherwise reply with text. Each
alternative is graded like any other exchange before any of it reaches the
client. The first approved alternative ends the response: the client receives
the original text, the notices, then the alternative's text and tool calls with
its finish reason, as one buffered completion or, for a streamed request, as the
remaining events of the same stream. `usage` stays the first attempt's and does
not count later generations' tokens. A refused alternative adds its own notice.
An alternative that repeats a refused call's name and arguments is refused
again with the earlier explanation, without being graded, whatever its call ID.
That check lasts for one client request and does not equate different arguments
with the same effect.

**After an escalation, or a third refused proposal**, the model is not asked for
another approach. One final generation asks it to stop and put the question to
the user with labelled options, and its text ends the response. The final
request sets `tool_choice: "none"` when the request offers tools (and leaves it
unset otherwise), so the model answers in text and cannot start a
provider-hosted tool. If the model proposes calls anyway, they are withheld
without being graded, and a fixed `WATCHER ESCALATION` or `WATCHER NOTICE`
question to the user follows its text. The same question is added when the
final reply asks the user nothing: it has no text, was cut off by the token
limit or the provider's content filter, or has no question mark. A complete
final reply that already asks a question is delivered unchanged. An approved
alternative without tool calls whose text is empty or cut off the same way ends
with the fixed question a failed alternative gets. A client request therefore
costs at most four model calls: its own, two alternatives and the final reply, and only the
first three can release calls.

The options offered depend on who escalated. Only Watcher's graders
(`policy_gateway` and `triage` decisions) read the conversation, so only then
is the model asked to offer "A. allow this call" and to let the user approve it
in their reply; Watcher grades the call again when it is proposed. A rule, a
threshold or the grading-failure policy would escalate the same call again, so
for those the options are to skip it, do something else or ask an administrator
to change the policy.

If a generation cannot be obtained, because the gateway or provider fails, its
response cannot be read or merged, Watcher does not evaluate an alternative or
its decisions do not match, or time runs out, the response ends with the
notices, a sentence saying why nothing followed and a fixed question asking the
user how to proceed, so the agent's turn never ends on a notice alone. Nothing from a failed
generation reaches the client. Unlike the LiteLLM example, these failures do
not turn the response into an error, since the client's own proposal was
cleanly refused. Failures on the client's own proposal return errors as
described in [Other responses](#other-responses) and never lead to
alternatives.

**One Watcher session.** Each alternative Watcher grades is submitted in the
client request's own session, the one named in `X-Watcher-Conversation-Id`.
Its history is the client's conversation plus the refused proposals and their
tool results. Those results are the processor's refusal receipts, not runs, and
Watcher records a call it first sees with a result as having run unless the
session already holds a decision for it. Grading in the same session lets
Watcher match those calls to the decisions it stored for the refused proposal,
so they are not recorded as run (see the storage-order limit below).
Every request declares that the processor withholds refused calls
(`withholds_refused_calls`), so Watcher records an enforced deny or escalation
as blocked rather than waiting for an outcome. An alternative refused for
repeating a refused operation is not submitted, since Watcher never graded it;
it and its receipts are also left out of the history later alternatives are
graded with, while the model still sees them. The processor logs
`alternative_repeated` for it. The final reply is not graded (the processor
logs `final_reply` with the number of calls it withheld).

After the client has the reply, the processor records it in the same session,
naming every call it withheld (`withheld_tool_use_ids`), including an approved
alternative's calls when the reply had to be shortened to fit the size limit.
Watcher shows those calls before the delivered reply. Calls the reply carries
were graded already, so the recording sends them as history rather than as new
calls. The recording never delays or changes the reply; a failure is logged as
`delivered_reply_not_recorded`. A Watcher server older than these two fields
rejects them; the processor then sends the exchange once more without them,
so it is still graded and recorded, with refusals left pending, and logs
`watcher_predates_gateway_fields`. Watcher stores exchanges asynchronously: if
it stores an alternative before the original proposal, an allowed call that was
withheld beside a refused one can still be recorded as completed, though the
refused call is still recorded as blocked. As elsewhere, a successful
submission acknowledges receipt, not storage. On the client's next turn, its
history includes the delivered notices and alternative.

**Time.** The client's proposal, each later provider call and each grade share
the processor's 420-second limit, so they only use what the first decision
left; Envoy's 450-second message timeout is never exceeded.

**Internal marker.** The alternative request passes through the processor
again. So that it is not graded twice, given a second system notice or
followed by alternatives of its own,
the processor signs it with an `X-Watcher-Alternative` header: an expiry and an
HMAC over the exact request body, keyed from `WATCHER_API_KEY`. A request with a
valid marker passes through without grading, and the requesting pass grades the
alternative itself. The header is removed before the request reaches the
provider. Clients cannot produce a valid marker without the Watcher API key, and
a request with an invalid one is refused with HTTP 403.

### Other responses

Missing, unmatched or contradictory decisions are not refusals: they replace a
buffered response with HTTP 403 and an OpenAI-style error whose `type` is
`watcher_withheld`, and end a streamed response with an equivalent error event.

Text-only responses are submitted too, so Watcher records the whole
conversation. Provider error responses (4xx and 5xx) carry no tool calls and
pass through without being submitted. Any other status, including 201, is
evaluated as a possible completion. Provider redirects are replaced with HTTP
502: OpenAI clients resend the request to a redirect's target, which would
fetch a completion from outside the gateway. Chunked provider responses are
evaluated once complete.

### Streaming

`stream: true` requests are supported. When the provider answers with server-sent
events, the processor switches that response to streamed processing (the
policy's `allowModeOverride`). Text reaches the client as it arrives. From the
first event carrying a tool call, the processor holds every event until the
provider finishes the stream. Chat Completions has no marker for when one tool
call's arguments are complete, so the whole response must arrive before Watcher
can decide. The processor then assembles the events into one completion for
Watcher and either releases the held events or ends the stream. A Watcher
refusal drops the held events and ends the stream normally with the denial
notice described above and any approved alternative. A technical failure cannot be an HTTP status once the
response has started, so the processor instead sends one SSE error event with
`type: watcher_withheld`, which OpenAI clients raise as an error. Its `code` is
403 when the response cannot be verified and 503 when Watcher was unavailable. Text-only streams are submitted when the provider
finishes, and the final `[DONE]` event waits until Watcher acknowledges that
submission. As with buffered responses, acknowledgement is not proof of storage,
and a client that disconnects earlier can still cut the submission short.
Envoy cannot send keepalives from the processor, so a client sees no bytes while
Watcher grades.

The processor rewrites line endings to LF before checking events, so it parses
exactly what OpenAI clients parse whether the provider uses LF, CRLF or CR. With
lone CR line endings an event is released only when the next byte arrives,
since until then its final CR could be the start of a CRLF.
Clients stop at `[DONE]` and treat a choice as complete at its `finish_reason`;
a stream that continues past either is ended with an error event, since the
extra data could change what Watcher grades without changing what the client
receives.

### Request and response formats

The route accepts OpenAI Chat Completions with one choice and client function
tools. Multiple choices, legacy `functions`, audio output and other API paths
return HTTP 400 or 404 before the provider is called.
Every tool call ID in a response must be unique, and arguments must be a JSON
object. Watcher handles provider message conversion; local verification covers
text conversations.

Agent Router's own processor runs before this one on the request path and after
it on the response path. This processor therefore sees the provider's response
before Agent Router translates it into Chat Completions format. Use backends
with the `OpenAI` schema only, as in the supplied configuration. With another
schema, such as `AWSBedrock`, the processor cannot read the provider's format
and withholds every response with HTTP 403. The processor also removes the
client's `Accept-Encoding` header so the provider responds uncompressed; it
withholds compressed responses it cannot read.

Permanent Watcher rejections, such as an unconvertible exchange, withhold the
response with HTTP 403. Connection errors, timeouts, rate limits and server
failures return HTTP 503. There is no durable delivery queue or replay. The
processor logs one `exchange_withheld` event, with `structlog`, for every request
or response it refuses. The event holds the HTTP status, the reason, the
conversation ID once one exists, and any Watcher status or error type. It never
contains request or response content. Envoy's own failures, such as an
unreachable processor, appear only in Envoy's logs.

The processor can stop tool calls before a client receives them. It cannot stop
tools a provider runs itself, prove that a client executed a released call, or
capture tool results a client never sends in a later request. It does not
monitor other Gateways or direct provider calls that bypass the gateway. The
processor rejects every path except Chat Completions, so Agent Router's MCP
gateway (`/mcp`) is not expected to work on a Gateway with this policy; this
was not tested. Serve MCP from a separate Gateway.

## Tests

`src/watcher_agent_router/exchange.py` holds the Watcher SDK contract and
`alternatives.py` the alternative requests and `processor.py` the Envoy external
processor. `gateway/` holds the Agent Router
configuration. `metadata.yaml` records the tested versions and scope.

The unit tests drive the processor with Envoy's protobuf messages and a
simulated Watcher API:

```sh
uv run pytest tests --ignore tests/native
```

The native tests start the installed `aigw` CLI with the supplied configuration,
the processor, a local OpenAI-compatible provider and a simulated Watcher API,
then call the gateway with the OpenAI client and the demo. They also check
streaming (text arriving before the provider finishes, a denied streamed call
never reaching the client), redirects, chunked and 201 responses, Envoy's applied timeouts, that a
15-second grade is still delivered, that stopping the processor mid-grade
withholds the response, and, with `GATEWAY_URL` pointing back at the gateway,
that buffered and streamed refusals are followed by alternatives requested
through Agent Router and that a client cannot use the internal marker:

```sh
AIGW_BIN=/path/to/aigw uv run pytest tests/native
```

They change only the provider endpoint, its TLS policy and the listener port in
the configuration. The first run needs network access to download Envoy.
Simulated model and Watcher responses exercise the gateway wiring, not model
quality, a real Watcher server or hosted provider availability.

To also send traffic through a real Watcher API, set `WATCHER_LIVE_BASE_URL`
(and `WATCHER_LIVE_API_KEY`, unless the server is a local development server
that accepts unauthenticated requests):

```sh
AIGW_BIN=/path/to/aigw WATCHER_LIVE_BASE_URL='https://your-watcher-server/api' \
  WATCHER_LIVE_API_KEY='your-watcher-api-key' uv run pytest tests/native/test_live_api.py
```

These tests read each exchange back through the SDK, require the Gateway
source label, and require that a dangerous tool call reaches the client only
when the decision Watcher stored allows it. The provider is still simulated, and
the decision itself depends on your server's policy and grading models.

`tests/native/test_live_withheld.py` uses the same variables. It replaces the
organization's managed settings with two command rules while it runs (deny
`write_file`, allow `read_file`) and restores them afterwards, so point it only
at a development server. It reads every session stored during each case and
requires that a refused call is recorded as blocked, and that neither its
withheld sibling nor a locally refused repeat is recorded as having run.
