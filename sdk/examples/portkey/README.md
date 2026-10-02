# Portkey gateway

Install Watcher on a Portkey gateway so existing clients are monitored without
importing Watcher or changing their tool dispatcher. The server launcher adds
mandatory native Portkey webhooks to every request on its Chat Completions route.
The webhooks call a private Python service that uses the public Watcher SDK.

The same installation follows the Watcher organization's settings. In enforce
mode, the gateway withholds responses containing denied or escalated tool calls.
In observe or paused mode, it releases the response and preserves the client's
normal tool permissions. It does not implement an interactive approval screen;
requests that need a human are withheld.

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
applied decision: `allow` and `deferred` release the native response; `deny`,
`escalate`, missing results and mismatched call IDs withhold the whole response.
A configured grading-failure allow is respected as server policy. A bridge or
Watcher transport failure also withholds the response, including in observe mode.

Portkey returns HTTP 446 for a rejected guardrail. No executable tool call from
that response should reach the client. The callback cannot stop a tool a client
runs independently of gateway output. Unsupported streaming is rejected before
the provider call because the pinned Portkey response-hook path cannot enforce
its post-response verdict on a stream.

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
a container with external networking disabled. Reports include JUnit results,
runtime versions, source hashes and the native executable/plugin identities.
Dependency downloads happen during the build; the test phase is isolated.

Run the bridge's contract tests without network access:

```sh
../run-without-network.sh .venv/bin/python -m pytest --noconftest -c pyproject.toml tests/test_bridge.py
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
