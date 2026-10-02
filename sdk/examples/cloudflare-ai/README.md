# Cloudflare AI Gateway log ingestion

Import completed requests from Cloudflare AI Gateway's encrypted Workers Logpush
exports into Watcher. Logging and export are configured on the gateway, so
clients do not install Watcher. The importer uses the public Watcher SDK.

This is post-request transcript ingestion. It cannot hold a gateway response,
block a tool call or provide synchronous monitoring. It is an example, not an
officially supported Cloudflare integration.

## Configure gateway exports

Enable logging on the gateway, generate an RSA key pair and upload its public
key to the gateway's settings. Keep the private key with the importer. Then
create and enable a Workers Logpush job for the AI Gateway dataset, delivering
to your object storage. Both the public-key configuration and Logpush job are
required. Cloudflare requires its Workers Paid plan for this feature.

Follow Cloudflare's [Workers Logpush setup](https://developers.cloudflare.com/ai-gateway/observability/logging/logpush/)
for the gateway and storage configuration. The importer does not configure
Cloudflare or download objects automatically.

## Install and import

Use Python 3.12 or newer and `uv`:

```sh
uv sync --python 3.12
export WATCHER_BASE_URL='https://your-watcher-server/api'
export WATCHER_API_KEY='your-watcher-api-key'
```

The Watcher credential needs `sessions:ingest`. The development environment uses
the adjacent SDK source directory. For a release wheel, follow the
[shared setup guide](../README.md). Run `uv build --wheel` to package the importer.

Download a Logpush object and keep its original storage key. Run:

```sh
uv run watcher-cloudflare-import import-file \
  ./downloaded-log.jsonl.gz ./private-key.pem \
  'my-account/my-gateway' 'exports/original-object-key.jsonl.gz'
```

The arguments are the local file, RSA private-key file, gateway namespace and
original storage object key. The namespace is an operator-chosen identifier for
this gateway. The importer decrypts each record's `RequestBody` and `ResponseBody`
using Cloudflare's RSA-OAEP-SHA256 and AES-256-GCM envelope. The private key stays
local and is not included in output or SDK requests.

The command prints the submitted count and Watcher conversation identifiers of
the form `cloudflare:<digest>`. Find those identifiers in Watcher and verify the
stored messages, tool IDs and results. A successful submission is not a durable
storage acknowledgement; recording occurs after the hook response. The
`cloudflare:` prefix makes the Analyzer show these sessions with the Gateway
source.

## Scope and recovery

The importer accepts JSONL or gzipped JSONL, with at most 10,000 records per file
and 1 MiB per decompressed record. Split larger downloads before importing.
Cloudflare's own logging limits, retention and export settings can omit requests
before the importer sees them.

Each record becomes a separate snapshot. Its identity incorporates the gateway
namespace, original object key, record position and bytes. Identical requests in
different records remain separate. Re-importing the same object with the same
namespace and object key reuses its identifiers; this is not a delivery ledger
or a guarantee of exactly-once storage.

Only complete textual Chat Completions request/response objects are supported.
Native tool IDs, JSON arguments, visible history and tool results are retained.
Raw SSE bodies, other provider formats, multimodal content and incomplete
responses are rejected. A streamed gateway request is importable only if the
export contains a complete Chat JSON response.

The command stops on the first decryption, format or SDK failure. Earlier
records may already have been submitted. Keep the original file and check those
identifiers before retrying. There is no background queue or automatic retry.

## Verification and layout

Cloudflare AI Gateway is a hosted service. Local encrypted fixtures verify the
documented encryption envelope and supported record shapes; they cannot prove
hosted emission, delivery or streaming-log encoding. Verify a captured export
from your gateway before depending on complete audit coverage.

`src/watcher_cloudflare_ai/` contains the importer and format conversion.
`tests/` covers authenticated decryption, malformed and partial records,
identity separation, size limits and public-SDK submission. `metadata.yaml`
records verified versions and test scope.

```sh
env -i PATH="$PATH" ../run-without-network.sh "$PWD/.venv/bin/python" \
  -m pytest --noconftest -c pyproject.toml tests
```

Install dependencies before entering network isolation.
