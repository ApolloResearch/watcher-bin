# OpenRouter Broadcast ingestion

Receive OpenRouter Broadcast traces and submit their captured conversations to
Watcher through the public SDK. Broadcast is enabled centrally for your
OpenRouter account; clients do not need a Watcher wrapper.

Broadcast runs after a request completes. This example ingests transcripts and
cannot withhold model responses or enforce tool permissions. It is an example,
not an officially supported OpenRouter integration.

## Install the receiver

Use Python 3.12 or newer and `uv`:

```sh
uv sync --python 3.12
export WATCHER_BASE_URL='https://your-watcher-server/api'
export WATCHER_API_KEY='your-watcher-api-key'
export OPENROUTER_WEBHOOK_TOKEN='a-long-random-private-secret'
uv run watcher-openrouter-receiver serve my-openrouter-account \
  --host 127.0.0.1 --port 8765
```

The Watcher credential needs `sessions:ingest`. The namespace argument is an
operator-chosen identifier for the account. The development environment uses
the adjacent SDK source directory; see the [shared setup guide](../README.md)
for release-wheel installation. Build this package with `uv build --wheel`.

The receiver accepts authenticated POST and PUT requests at `/v1/traces`.
Place it behind your TLS ingress and configure request limits there. OpenRouter
needs to reach that ingress; a loopback address is suitable only for local
testing. This example does not deploy a public endpoint.

## Configure Broadcast

In OpenRouter's Settings → Observability, enable Broadcast and configure its
Webhook destination. Set the URL to your receiver's HTTPS `/v1/traces` address
and configure this custom header:

```json
{"Authorization": "Bearer your-webhook-token"}
```

Use the same token as `OPENROUTER_WEBHOOK_TOKEN`. Disable Privacy Mode for this
destination if you want transcripts; a metadata-only trace is insufficient.
Run OpenRouter's connection test, then send a normal model request through the
gateway. Follow the [OpenRouter webhook guide](https://openrouter.ai/docs/guides/features/broadcast/webhook)
for account configuration.

The receiver returns counts of submitted generations and ignored non-generation
spans, with Watcher conversation identifiers of the form `openrouter:<digest>`.
Verify those identifiers and their stored transcripts in Watcher. HTTP success
acknowledges submission, not durable storage; recording happens after the hook
response. The `openrouter:` prefix makes the Analyzer show these sessions with
the Gateway source.

## Supported content and limits

The receiver reads the generation-span attribute pairs `gen_ai.prompt` /
`gen_ai.completion` or `span.input` / `span.output`. It supports JSON-encoded
complete Chat request/response objects and JSON-encoded arrays of Chat messages.
For message-array inputs, `gen_ai.request.model` must identify the model.

These supported shapes are exercised locally. OpenRouter documents the attribute
names but the example has no verified hosted payload capture. Confirm that your
account emits a supported shape before relying on transcript coverage. Unsupported
encodings, privacy-mode omissions, multimodal content and explicit incomplete
response-object finish states
produce an error instead of a partial transcript.

Each generation becomes a separate snapshot. Its identity incorporates the
receiver namespace and full span, including its span ID and timestamps.
Client-supplied `session.id` values do not combine different users' transcripts.
Repeated identical spans reuse identifiers, without promising exactly-once
storage. The receiver has no durable queue.

The complete batch is validated before submission. If a later SDK call fails,
earlier generations may already have been accepted; retain the source delivery
before retrying. The receiver accepts bodies up to 8 MiB and at most 1,000
content-bearing generations per delivery.

## Tests and directory layout

`src/watcher_openrouter/` contains the receiver and format conversion. `tests/`
covers attribute parsing, source identity, missing content and public-SDK
submission. `metadata.yaml` records verified versions and scope. Local tests do
not establish hosted Broadcast emission or delivery.

```sh
env -i PATH="$PATH" ../run-without-network.sh "$PWD/.venv/bin/python" \
  -m pytest --noconftest -c pyproject.toml tests
```

Install dependencies before entering network isolation.

Message-array exports do not carry an independent completion indicator. They can
contain only a partial reply; the importer preserves the supplied messages and
cannot establish that the model finished. Response objects with an explicit
incomplete finish state are rejected.
