# Helicone gateway observation

Receive Helicone's signed completion webhooks and send the logged request and
response to Watcher through the public SDK. Configure the webhook centrally in
Helicone; applications already using the monitored gateway do not import Watcher
or change their tool dispatcher.

This is an **observation integration**. Helicone sends completion events after the
response has reached the client. The receiver cannot stop tools, obtain human
approval, or make a retrospective denial count as enforcement. It submits
transcripts through the hook endpoint without creating applied tool decisions.

Helicone's gateway documents no plugin or middleware hook that asks an external
service before a response is delivered. To enforce Watcher's decisions, put one
of the enforcing gateway examples in front of the clients:
[LiteLLM](../litellm/README.md), [Agent Router](../agent-router/README.md),
[Bifrost](../bifrost/README.md), [Kong AI Proxy](../kong-ai/README.md) or
[Portkey](../portkey/README.md). In enforce mode, these examples check supported
client-executed tool calls before delivering them and withhold calls Watcher
refuses; buffering and supported APIs vary by example. Using Helicone as such a
gateway's OpenAI-compatible upstream is not tested in these examples.

## Supported data

The receiver accepts completed OpenAI Chat Completions records containing text
messages and function tools. It preserves native tool IDs and JSON argument types.
It accepts Helicone's object and JSON-string body representations, including
complete JSON responses assembled by the platform from streaming requests. Raw
SSE, multimodal content, other provider formats, multiple completion choices and
incomplete responses are rejected. Ancillary message fields, including `name`
and unknown provider extensions, are not exported.

Enable request and response content logging in Helicone. Privacy settings that
remove content cannot be reversed by this receiver. Each logged request becomes
a separate Watcher snapshot under `helicone:<request_id>`. Redelivery keeps that
identity; the receiver does not merge requests by user or API key.

## Install and start

Use Python 3.12+ and uv. From this example directory:

```sh
uv sync --python 3.12
export WATCHER_BASE_URL=https://your-watcher-server/api
export WATCHER_API_KEY=your-ingest-key
export HELICONE_WEBHOOK_SECRET=your-helicone-webhook-hmac-key
.venv/bin/python -m watcher_helicone.receiver serve --host 127.0.0.1 --port 8766
```

The receiver checks `sessions:ingest` permission before opening its listener.
Session-read permission is not required for normal ingestion.

Put the listener behind your authenticated TLS deployment or provide
`--certfile /path/certificate.pem --keyfile /path/private-key.pem` to serve TLS
directly. Helicone requires an HTTPS destination. Keep the HMAC key and Watcher API
key in your server's secret store or environment, not client applications.

## Configure Helicone

This receiver targets the completion-webhook format at
[Helicone revision `067d929`](https://github.com/Helicone/helicone/commit/067d9290acb4f1fc9320e902fc67b4b399b50363).
Compatibility with a running Helicone platform has not yet been verified. Check
your deployed version before relying on its signing and body-reference behavior.

In the Helicone platform, create a completion webhook pointing to your receiver's
`/webhook` route. Use the webhook's HMAC key as `HELICONE_WEBHOOK_SECRET`. Select the
requests you intend to observe and set the sample rate accordingly. For complete
coverage, use a 100% sample rate without excluding relevant traffic.

The receiver verifies `Helicone-Signature` against the exact request bytes before
parsing data or fetching any object. A valid event with unsupported or missing
content returns an error; it does not produce an empty successful transcript.

For a self-hosted deployment, the gateway must send its logs to the Helicone
platform. The lightweight AI Gateway alone does not emit the platform's configured
webhooks. Keep gateway logging, the platform API, its databases and object storage
available. See the [Helicone self-hosting guide](https://docs.helicone.ai/getting-started/self-host/docker).

## Larger bodies

When inline content is unavailable, the receiver can fetch the event's signed
`request_response_url`. Enable **Include Data** in Helicone and explicitly allow
your storage origin:

```sh
.venv/bin/python -m watcher_helicone.receiver serve \
  --body-origin https://your-storage-host.example
```

Repeat `--body-origin` for additional trusted origins. Matching includes the
scheme, hostname and port; wildcards are not accepted. Redirects, URL credentials
and compressed bodies are rejected. Watcher credentials, webhook secrets and
caller cookies are not forwarded to storage. Webhook and downloaded bodies each
have an 8 MiB limit.

An explicit HTTP origin can be used for isolated local object storage. Use HTTPS
for networked deployments. Signed URLs are credentials: retain them only as long
as needed and do not place them in logs or error messages.

## Delivery and verification

HTTP 200 means signature validation, conversion and the Watcher hook request
completed. Watcher schedules ingestion after its hook reply, so this is not a
durable storage acknowledgement. The response includes the external conversation
ID for lookup, which has the form `helicone:<request ID>`. Verify the matching
snapshot in Watcher with a separate read-capable credential when needed. The
`helicone:` prefix makes the Analyzer show these sessions with the Gateway source.

Helicone's sampling, content retention and delivery behavior determine which
events arrive. The receiver has no persistent queue and does not promise a
complete change feed. Retain source records if your deployment requires replay;
resending an event uses the same logged request ID.

Run contract and security-boundary tests with networking disabled:

```sh
../run-without-network.sh .venv/bin/python -m pytest --noconftest -c pyproject.toml tests
```

Those tests validate authentic HMAC construction, object/string bodies,
credential-free bounded retrieval and transcript-only SDK requests. They do not
substitute for a running Helicone platform. For signed local webhooks through an
installed receiver and the real Watcher API/database, see the
[receiver verification fixture](tests/native/README.md). `metadata.yaml` names
the completed native and Watcher verification scope.
