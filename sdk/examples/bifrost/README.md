# Bifrost gateway

Install this native HTTP transport plugin in Bifrost to monitor ordinary clients
at the gateway. It captures client-facing Chat Completions requests and responses
and calls a private Python service using the public Watcher SDK. Clients do not
import Watcher or opt into a separate tool dispatcher.

The same plugin follows Watcher's observe, enforce and paused settings. Applied
allow or deferred decisions release the response. When Watcher denies or
escalates a call, the client never receives it: the gateway asks the model for
another approach and returns an ordinary completion with Watcher's notice and
any approved alternative (see [Refused calls](#refused-calls)). A call requiring
human approval is never released automatically; the model is asked to put the
decision to the user. This example does not provide a human approval screen.

## Supported traffic

The plugin supports `/openai/v1/chat/completions` with text messages,
client-executed function tools, one response choice.
Other inference routes and unsupported message formats are rejected.
Provider-hosted tools and Bifrost MCP tools require different interception points
and are outside this plugin's scope. Keep those routes inaccessible to clients
that require this policy.

Buffered JSON responses are checked before delivery. For Chat Completions streams,
the plugin suppresses original chunks, assembles the complete text and function
arguments, and checks the response when the provider sends its finish marker.
It then emits one newly encoded completion delta containing the evaluated
message, or the replacement completion after a refusal, followed by `[DONE]`.
The stream therefore loses incremental delivery. Incomplete or oversized streams
release no executable tool calls. The body limit is 8 MiB. Buffered replies that
exceed it, have no body, or lose their original request context are replaced with a
refusal response.

Each exchange has a gateway-generated identifier of the form
`bifrost:<random hex>`. Buffered responses return it in
`X-Watcher-Conversation-Id`. For generic Chat Completions clients, each exchange
creates a separate Watcher session containing the supplied full history; identical
prompts and shared API keys do not join those sessions. Decisions remain attached
to the exchange where they were graded.

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

The bridge refuses identifiers without the `bifrost:` prefix. The prefix makes
the Analyzer show these sessions with the Gateway source; use the
`watcher-gateway` session source filter for these gateway captures.
Legacy captures with an `api_capture` metadata object but no `transport` field
retain the `tailscale-aperture` source label. That legacy label does not identify
which gateway supplied the capture.

## Install

Use Python 3.12+, uv, the pinned Bifrost source, and Go 1.27.0. Native Go plugins
must be compiled with the same toolchain, dependency versions and build flags as
the gateway binary. An arbitrary downloaded Bifrost binary is not interchangeable
with a locally compiled plugin.

From this example directory, install the Python bridge:

```sh
uv sync --python 3.12
```

Check out Bifrost at `048492cff9cf451baf7bfcb13bc0342383788f15`. Copy
`gateway/main.go` into a plugin module in that source tree and include it alongside
Bifrost's core, framework, transport and plugin modules in the Go workspace. Build
the HTTP gateway and `watcher.so` with matching `-trimpath` settings; compile the
plugin with `-buildmode=plugin`. See Bifrost's
[HTTP transport plugin example](https://github.com/maximhq/bifrost/tree/048492cff9cf451baf7bfcb13bc0342383788f15/examples/plugins/http-transport-only)
for the native module layout.

## Configure

Set the following on the gateway and bridge processes:

```sh
export WATCHER_BASE_URL=https://your-watcher-server/api
export WATCHER_API_KEY=your-watcher-key
export WATCHER_BRIDGE_URL=http://127.0.0.1:8765
export WATCHER_BRIDGE_TOKEN=your-private-bridge-secret
export WATCHER_GATEWAY_URL=http://127.0.0.1:8080
```

`WATCHER_GATEWAY_URL` is the origin of Bifrost's own client listener (no path).
The bridge sends alternative requests there, to `/openai/v1/chat/completions`.
`WATCHER_ALTERNATIVE_HEADERS` is only for operator-defined headers that Bifrost
governance is configured to require (`required_headers`): list them,
comma-separated, on both the gateway and the bridge so alternative requests
carry them too. Authentication, key-selection and session headers are forwarded
without it.

Start the bridge from this example directory:

```sh
.venv/bin/python -m watcher_bifrost.bridge serve --port 8765 --allow-buffered-stream
```

Add the compiled plugin to Bifrost's `config.json`, alongside your existing
provider and authentication configuration:

```json
{
  "plugins": [
    {"name": "watcher", "enabled": true, "path": "/absolute/path/watcher.so"}
  ]
}
```

Restart Bifrost with that configuration. Keep its normal authentication enabled
and the bridge on loopback or a private service network. Expose only the covered
Chat Completions route to clients; do not expose administration, MCP, Realtime or
other listeners as alternate unmonitored paths. The plugin refuses to initialize
without valid bridge configuration.

Ordinary OpenAI-compatible clients use the Bifrost OpenAI route. For a plain HTTP
example, set `GATEWAY_URL` to that route's `/v1` base, `GATEWAY_API_KEY` to the
normal Bifrost credential and `PROVIDER_MODEL`, then run
`.venv/bin/python demo/client.py`.

## Decisions and recording

A response is released only when every client-visible tool proposal has an
applied allow or deferred result for its unique native tool-call ID.
A skipped or missing result withholds the whole response, even when Watcher
returned an empty list. Text-only responses are also submitted for ingestion.

The bridge sends the original request and completed response bodies to
`pre_tool_use_hook`, together with the real client User-Agent, endpoint path and
provider. Watcher converts the transcript on the backend. No settings override is sent. Watcher performs the complete
configured policy flow. It may explicitly allow a grading failure under the
organization's failure policy; the plugin respects that applied outcome. Transport
errors, missing results and mismatched IDs withhold the response.

The gateway preserves the client's own permission checks when Watcher returns
deferred. It cannot prevent tool execution a client starts independently of the
model's returned calls. Stream errors may arrive after HTTP 200, but no held tool
arguments are released when the check fails.

### Refused calls

Coding agents end their turn on a text-only reply or an HTTP error, so a refusal
is answered with another proposal instead of an error. Nothing from a refused
response reaches the client until a replacement has been checked:

1. Every request gets a fixed system message, after the client's leading system
   and developer messages, telling the model that `WATCHER NOTICE` and
   `WATCHER ESCALATION` lines in its earlier replies were written by Watcher.
   The text is identical on every request, so prompt caching is unaffected. The
   provider and Watcher both see the request with this message, re-encoded as
   compact JSON; a request that no longer fits the 8 MiB body limit with it is
   refused.
2. When Watcher denies a call, all calls in that response are withheld. The
   bridge appends the refused assistant message and one tool result per call
   (Watcher's reason, or "did not run because Watcher refused another call") and
   asks the model for another approach. Tools and tool choice are unchanged.
3. The alternative is generated by a request to Bifrost's own Chat Completions
   route with the original client's authentication, key-selection and session
   headers (`Authorization`, `api-key`, `x-api-key`, `x-goog-api-key`,
   `x-bf-vk`, `x-bf-api-key`, `x-bf-api-key-id`, `x-bf-direct-key`,
   `x-bf-session-id`, `x-bf-session-ttl`, `x-bf-session-affinity`, and the
   harness session headers Bifrost derives a session from:
   `x-claude-code-session-id`, `x-session-affinity`, `x-session-id`,
   `session-id`, `session_id`, `thread-id`, `conversation_id`), plus any listed
   in `WATCHER_ALTERNATIVE_HEADERS`. The same virtual key, stored or direct
   provider key, session binding, routing, budgets and governance apply. No
   other client header is forwarded. The headers are held in memory for that request only and never
   logged.
4. The alternative is checked as its own exchange in the client's Watcher
   session, where Watcher has its own decision for each withheld call that the
   alternative's history reports as not run, so it does not record those calls
   as completed. A call repeating a refused operation (same tool and arguments
   under any call ID) is refused again without being graded, and its turn is
   left out of the history later alternatives are graded against. An allowed
   alternative is delivered as one completion: the original text, the notices,
   then the alternative's text and calls. Watcher stores exchanges
   asynchronously; if it stores an alternative before the original proposal,
   an allowed call withheld with the refused one can still end up recorded as
   completed. A refused call is recorded as blocked either way.
5. At most three proposals are checked per client request (the client's and two
   alternatives). After an escalation, or a third refused proposal, one last
   generation with `tool_choice: "none"` asks the model to stop and ask the user,
   with labelled options. "Allow" is offered only for escalations from Watcher's
   graders; rule, threshold and grading-failure escalations offer skip, another
   approach, or asking an administrator. If that generation proposes calls
   anyway, they are withheld without being sent to Watcher and a notice asks the
   user how to proceed. The same notice is added when that generation asks the
   user nothing (no text, cut off by the output limit or the content filter, or
   no question mark), and when it fails, after a sentence saying why no final
   reply followed. A complete final reply that already asks a question is
   delivered unchanged.
6. A provider failure, an unreachable gateway, an unverifiable alternative, a
   Watcher error, Watcher decisions that do not match the alternative or the
   time limit ends recovery: the response ends with the notices, a sentence
   saying why nothing followed and a fixed question asking the user how to
   proceed, so the agent's turn never ends on a notice alone. No call from that
   attempt is released.

A request asking for JSON output (`response_format` of type `json_object` or
`json_schema`) cannot carry a text notice, so a refusal there gets HTTP 403 with
an OpenAI-style `watcher_withheld` error (a stream error for streams) and no
alternative is generated.

The original decision and the whole recovery share one 420-second limit, below
the plugin's 425-second bridge timeout. If Watcher cannot make the original
decision, the response is still replaced with HTTP 403.

The alternative request carries an `X-Watcher-Alternative` header: an expiry and
an HMAC over the expiry and the exact request body, keyed from the Watcher API
key, which only the bridge holds. On that nested pass the plugin asks the bridge
to verify it; a valid marker skips grading, the system message and recovery, and
is accepted only once. A missing, malformed, expired, reused or mismatched marker
gets HTTP 403. Bifrost's plugin interface cannot delete request headers, so the
plugin replaces the marker with an empty value before Bifrost builds the
provider request.

Every exchange tells Watcher that the gateway withholds refused calls
(`withholds_refused_calls`), so an enforced deny or escalation is recorded as
blocked as soon as it is decided. After a replacement completion has been
sent, the bridge records it in the client's session as the client received it,
naming every call withheld in its favour (`withheld_tool_use_ids`: refused
calls and the calls withheld with them, never a delivered call), so the
Analyzer shows those calls before the delivered reply. Calls the replacement
delivers were already graded as the approved alternative and are not graded
again. This recording runs after the reply and never delays or changes it; a
failure is logged. A Watcher server older than these fields rejects them, and
the bridge then sends the exchange once more without them, so refusals stay
pending there.

Observe and paused modes release responses unchanged, with no notice.

Watcher ingestion follows the hook reply asynchronously. A successful hook is not
a storage receipt. The SDK key needs ingestion and monitoring permission. Query
the matching snapshot in Watcher to verify stored messages and decisions.
Subsequent requests record tool results and final replies when supplied in their
full history. For generic clients, these are separate sessions and historical
judgments are not copied into the later snapshot.

## Verify locally

For a complete installed-artifact test, use Python 3.12, uv and Docker, then run:

```sh
tests/native/run.sh
```

The recipe downloads checksum-pinned gateway and toolchain archives, builds the
SDK and example wheels, and checks their installed bytes before running tests.
It runs the actual gateway with local provider and Watcher protocol fixtures in
a container with external networking disabled. Reports include JUnit results,
runtime versions, source hashes and the native executable/plugin identities.
Dependency downloads happen during the build; the test phase is isolated.

A C compiler, curl and tar are also required to build the gateway and Go plugin.

Run bridge contract tests with networking disabled:

```sh
../run-without-network.sh .venv/bin/python -m pytest --noconftest -c pyproject.toml tests
```

Build an API-only local test gateway and matching plugin with Go 1.27.0, a C
compiler, curl and tar. Dependency downloads happen during this step:

```sh
bash tests/native/build.sh
```

This prints the two binary paths and saves source/build checksums. Its embedded UI
is not built; use the regular Bifrost deployment build for an interactive UI.
The complete recipe above checks the compiled gateway and plugin hashes before
any model traffic and preserves the build information with its reports.

The probe runs the actual gateway and plugin with local provider and Watcher
protocol fixtures. It does not establish Watcher persistence. The backend test
driver supplies a real local Watcher relay and verifies stored records through
the public SDK. `metadata.yaml` records the completed verification scope.

The bridge checks the public permission endpoint at startup and refuses to start
without `sessions:ingest`. It does not require session-read permission to run.

Buffered text-only replies stopped by an output limit or content filter are
submitted and delivered unchanged. Incomplete responses containing tool proposals
are withheld in every mode; the integration never executes a partial proposal.
