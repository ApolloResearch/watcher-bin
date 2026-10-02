# Watcher exports through OpenTelemetry

Export Watcher tool-call decisions, session summaries and optional transcripts as
OpenTelemetry logs to Grafana/Loki,
Datadog, Elastic Cloud, New Relic, Dynatrace, CloudWatch Logs or OpenSearch. The
examples share one exporter and use the OpenTelemetry Collector for destination
authentication and transport.

The exporter reads a chosen time window. It does not ingest agent telemetry,
monitor tools synchronously or provide a complete live audit feed. These are
examples to adapt, not officially supported connectors.

## How it works

```text
Watcher API → public Watcher SDK → OTLP logs → Collector → destination log store
```

The default decision export contains Watcher's session and tool-call IDs, severity when available,
decision category, coverage and content-availability state. The body is fixed
text: `Watcher recorded a tool-call decision.` Transcript content, tool arguments,
tool names and user identity are excluded. Scrubbed records retain their available
decision fields. Watcher gateway/triage severity uses a 1–10 scale and is forwarded
unchanged as `watcher.severity_score`; the exporter neither clamps it nor maps it
to an OpenTelemetry log level. No trace or span IDs are invented.

## Install and run

You need Python 3.12 or later, [uv](https://docs.astral.sh/uv/), a Watcher API key
with permission to read the selected sessions, and the
[OpenTelemetry Collector Contrib](https://opentelemetry.io/docs/collector/installation/).

From this directory in the SDK source checkout:

```sh
uv sync
otelcol-contrib --config=config/collector-local.yaml
```

In another terminal, set the Watcher server and a timezone-aware window that
contains decisions you are permitted to export:

```sh
export WATCHER_URL='https://your-watcher-server/api'
export WATCHER_API_KEY='your-watcher-api-key'
export WATCHER_EXPORT_START='2026-09-18T10:00:00Z'
export WATCHER_EXPORT_END='2026-09-18T11:00:00Z'
export OTLP_LOGS_ENDPOINT='http://127.0.0.1:4318/v1/logs'
uv run python demo/export.py
```

The command reports accepted record and batch counts. The local configuration
prints attributes without forwarding them. For another destination, stop that
Collector and start one of the configurations below; the export command stays
the same. Bind the Collector receiver to loopback as shown, or secure it before
making it reachable by other machines. Store credentials outside source files. An unset credential variable can become
an empty header without preventing Collector startup; check the required values
before starting and verify records in the destination.

## Destination examples

| Destination | Configuration | Local verification | Setup and indexed-record check |
| --- | --- | --- | --- |
| Grafana Cloud | [collector-grafana.yaml](config/collector-grafana.yaml) | Real Collector and header-forwarding fixture | [Grafana and Loki](#grafana-and-loki) |
| Self-managed Loki | [collector-loki.yaml](config/collector-loki.yaml) | Real Collector; optional real Loki storage/query fixture | [Grafana and Loki](#grafana-and-loki) |
| Datadog | [collector-datadog.yaml](config/collector-datadog.yaml) | Real Collector and header-forwarding fixture | [Datadog](#datadog) |
| Elastic Cloud | [collector-elastic.yaml](config/collector-elastic.yaml) | Real Collector and header-forwarding fixture | [Elastic Cloud](#elastic-cloud) |
| New Relic | [collector-newrelic.yaml](config/collector-newrelic.yaml) | Real Collector; header forwarding, transient failure, rejection and partial-acceptance fixtures | [New Relic](#new-relic) |
| Dynatrace | [collector-dynatrace.yaml](config/collector-dynatrace.yaml) | Real Collector and classic-token header-forwarding fixture | [Dynatrace](#dynatrace) |
| CloudWatch Logs | [collector-cloudwatch.yaml](config/collector-cloudwatch.yaml) | Real Collector and independently checked SigV4 request | [CloudWatch Logs](#cloudwatch-logs) |
| Amazon OpenSearch Ingestion | [collector-opensearch.yaml](config/collector-opensearch.yaml) | Real Collector and independently checked SigV4 request | [OpenSearch](#opensearch) |
| Self-managed OpenSearch | [collector-dataprepper.yaml](config/collector-dataprepper.yaml) | Real Collector; optional Data Prepper and OpenSearch storage/query fixture | [OpenSearch](#opensearch) |

Hosted credentials, indexing, dashboards and alerts are not verified by the local
fixtures. The hosted checks below are operator instructions: run them in your
own authorized environment and select the exported occurrence-time range.

### Grafana and Loki

Grafana **Loki** stores logs; Tempo stores traces. For Grafana Cloud, copy the base
OTLP endpoint and complete authorization value from your
[connection tile](https://grafana.com/docs/grafana-cloud/observe-and-act/send-data/otlp/send-data-otlp/):

```sh
export GRAFANA_OTLP_ENDPOINT='https://your-grafana-otlp-endpoint/otlp'
export GRAFANA_OTLP_AUTHORIZATION='Basic your-encoded-credentials'
otelcol-contrib --config=config/collector-grafana.yaml
```

For self-managed Loki:

```sh
export LOKI_OTLP_ENDPOINT='http://127.0.0.1:3100/otlp'
otelcol-contrib --config=config/collector-loki.yaml
```

That configuration assumes a trusted local receiver. For a remote deployment,
use HTTPS and add your gateway's authentication and, if required, `X-Scope-OrgID`
tenant header. Loki needs structured metadata enabled, which is the default in
Loki 3 and later. Keep Watcher IDs as log attributes rather than index labels.
See the [Loki OTLP guide](https://grafana.com/docs/loki/latest/send-data/otel/).

After exporting, open Grafana Explore, choose your Loki data source and run:

```logql
{service_name="watcher-decisions"}
```

Inspect the fixed message and `watcher_tool_call_id`, `watcher_session_id` and
`watcher_severity_score` metadata. Loki normalizes dots to underscores. The local
service test also checks that Watcher IDs are not index labels.

### Datadog

Copy the complete site-specific OTLP logs URL from the
[Datadog OTLP logs guide](https://docs.datadoghq.com/opentelemetry/setup/otlp_ingest/logs/).
Use an ingestion API key for the destination organization:

```sh
export DATADOG_OTLP_LOGS_ENDPOINT='https://your-datadog-otlp-host/v1/logs'
export DD_API_KEY='your-datadog-api-key'
otelcol-contrib --config=config/collector-datadog.yaml
```

The configuration sends HTTP binary protobuf with `dd-api-key`. In Datadog Logs,
search `service:watcher-decisions`, open an event and inspect its `watcher.*`
attributes. If the service field is remapped by your pipeline, search the fixed
message and inspect the indexed fields. Check ingestion exclusions and retention
settings before treating an absent result as an exporter failure. This example
does not create Datadog monitors or Cloud SIEM rules.

### Elastic Cloud

Use the [Managed OTLP endpoint](https://www.elastic.co/docs/reference/opentelemetry/managed-inputs/managed-otlp-endpoint)
from the Elastic Cloud deployment or serverless project's connection details,
and an API key authorized for that endpoint:

```sh
export ELASTIC_OTLP_ENDPOINT='https://your-managed-otlp-endpoint'
export ELASTIC_API_KEY='your-elastic-api-key'
otelcol-contrib --config=config/collector-elastic.yaml
```

The Collector appends `/v1/logs` and sends `Authorization: ApiKey ...`. This is
not the legacy APM endpoint. The managed endpoint is not available for
self-managed Elasticsearch, ECE or ECK; those need an OTLP-compatible gateway
such as Elastic Agent.

In Kibana Discover, select the relevant `logs-*` data view and exported time
range, search `"Watcher recorded a tool-call decision."`, then inspect the
resource and Watcher ID attributes. The managed endpoint only writes to
`logs-`, `metrics-` or `traces-` data streams; this example leaves its default
log routing intact. Ingestion does not install Elastic Security detection rules.

### New Relic

Choose the [regional OTLP endpoint](https://docs.newrelic.com/docs/opentelemetry/best-practices/opentelemetry-otlp/)
and use the account's ingest/license key:

```sh
export NEW_RELIC_OTLP_ENDPOINT='https://otlp.nr-data.net'
export NEW_RELIC_LICENSE_KEY='your-new-relic-ingest-key'
otelcol-contrib --config=config/collector-newrelic.yaml
```

Use the EU or FedRAMP endpoint from that guide when applicable. The Collector
appends `/v1/logs` and sends `api-key`. New Relic's request limit is 1,000,000
bytes; the sender rejects requests larger than its default 900,000-byte budget before transmission.
The configuration forwards source batches without combining them.

In Logs, search the fixed message and inspect the Watcher ID attributes. Also
check `NrIntegrationError` events: New Relic can accept a request before
asynchronous payload validation rejects its contents. HTTP success alone does
not establish that every record became searchable. Alert conditions remain
operator configuration.

### Dynatrace

Use your environment API hostname, **not** its `.apps` UI hostname. With a
classic token authorized for `logs.ingest`:

```sh
export DYNATRACE_OTLP_LOGS_ENDPOINT='https://your-environment.live.dynatrace.com/api/v2/otlp/v1/logs'
export DYNATRACE_AUTHORIZATION='Api-Token your-classic-access-token'
otelcol-contrib --config=config/collector-dynatrace.yaml
```

A platform token uses `Bearer ...` with `openpipeline:logs:ingest`; ActiveGate
uses its environment-specific URL. See the
[Dynatrace OTLP API](https://docs.dynatrace.com/docs/ingest-from/opentelemetry/otlp-api).
The endpoint requires HTTP binary protobuf, which the configuration selects.
Only the classic-token header is exercised by the local fixture.

In Logs, select the exported time range, search the exact fixed message, open
one record and verify its session/tool-call references and severity attribute.
Check your OpenPipeline processing if fields are renamed. This example does not
configure Dynatrace problems, security events or alert rules.

### CloudWatch Logs

Create the log group and stream, choose their retention period and authorize an
AWS identity to ingest into them before starting. Supply credentials to the
Collector through your approved AWS credential provider, such as an IAM role;
the Watcher exporter does not implement signing or create AWS resources.

```sh
export AWS_REGION='us-east-1'
export CLOUDWATCH_OTLP_LOGS_ENDPOINT='https://logs.us-east-1.amazonaws.com/v1/logs'
export CLOUDWATCH_LOG_GROUP='watcher-decisions'
export CLOUDWATCH_LOG_STREAM='tool-call-decisions'
otelcol-contrib --config=config/collector-cloudwatch.yaml
```

The configuration signs requests with SigV4 service `logs` and sends
`x-aws-log-group` and `x-aws-log-stream`. Match the endpoint region to `AWS_REGION`.
The local fixture supplies synthetic credentials and independently verifies the
signature; it does not validate a real IAM policy. Use the
[CloudWatch OTLP endpoint guide](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/CloudWatch-OTLPEndpoint.html)
for account permissions and current limits.

CloudWatch rejects log timestamps more than 14 days old, more than two hours in
the future, or earlier than the log group's retention window. Records in one
request must also span no more than 24 hours, so choose recent export windows of
24 hours or less. Each request can contain at most 10,000 log events; the default
source batch contains 100 records. The conservative source request limit fits
the standard 1 MB request budget for these small decision records.

In Logs Insights, select the target log group and occurrence-time range:

```text
fields @timestamp, @message
| filter @message like /Watcher recorded a tool-call decision/
| sort @timestamp desc
| limit 20
```

Expand a record to check its Watcher IDs. Log acceptance does not create a
CloudWatch alarm or a Security Hub finding.

### OpenSearch

For **Amazon OpenSearch Ingestion**, create the pipeline and its domain/collection
sink first. The [AWS configuration guide](https://docs.aws.amazon.com/opensearch-service/latest/developerguide/configure-client-otel.html)
requires `osis:Ingest` for the ingestion identity, a pipeline role with destination
permissions, and matching source path and compression:

```sh
export AWS_REGION='us-east-1'
export OPENSEARCH_INGESTION_LOGS_ENDPOINT='https://your-pipeline.us-east-1.osis.amazonaws.com/watcher/v1/logs'
otelcol-contrib --config=config/collector-opensearch.yaml
```

Set your pipeline's logs path to `/watcher/v1/logs`, or change the endpoint to
its actual path. Use `compression: none` on that source to match the Collector.
The configuration signs with service `osis`; this endpoint is an ingestion
pipeline, not the domain's ordinary HTTPS search endpoint.

For **self-managed OpenSearch**, use Data Prepper's
[OpenTelemetry logs source](https://docs.opensearch.org/latest/data-prepper/pipelines/configuration/sources/otel-logs-source/):

```sh
export DATA_PREPPER_LOGS_ENDPOINT='https://your-data-prepper-host:21892/watcher/v1/logs'
otelcol-contrib --config=config/collector-dataprepper.yaml
```

The source needs `unframed_requests: true`, `path: /watcher/v1/logs` and
`compression: none`. Configure TLS, authentication and an OpenSearch sink for
your deployment. The [local service pipeline](tests/native/services/pipelines.yaml)
shows the source/sink relationship with authentication disabled only inside a
network-disabled fixture; it is not a production security configuration.

After exporting, use OpenSearch Dashboards Dev Tools against the configured
index (the local fixture uses `watcher-decisions`):

```json
GET watcher-decisions/_search
{
  "query": {"match_phrase": {"body": "Watcher recorded a tool-call decision."}},
  "size": 20
}
```

The local Data Prepper 2.11.0 pipeline stores fields such as
`log.attributes.watcher@tool_call_id` and `log.attributes.watcher@severity_score`.
Inspect those fields for Watcher IDs and severity. Other Data Prepper output
formats and AWS pipeline processors can change the mapping. OpenSearch Security Analytics needs
its own detector, field mapping and rules; indexing does not prove a detection.

## Request and record limits

The default `max_request_bytes=900_000` is this example's safety budget, not a
universal vendor limit. The configurations preserve source batches and do not
combine them. Gateway settings, per-record limits and destination processing can
still reject a smaller request; lowering the batch size does not fix a single
oversized record.

| Destination | Documented limits and operator checks |
| --- | --- |
| Grafana Cloud | [OTLP logs limits](https://grafana.com/docs/grafana-cloud/observe-and-act/send-data/otlp/otlp-format-considerations/#logs-ingestion-limits): 64 MB per request, 256 KB per line, and 128 structured-metadata attributes totaling at most 64 KB per log. |
| Self-managed Loki | Request budgets depend on your gateway and [Loki configuration](https://grafana.com/docs/loki/latest/configure/). Check the deployment's HTTP/body and per-stream limits; the separate gRPC receive limit is not a universal OTLP/HTTP body limit. |
| Datadog | [OTLP intake limits](https://docs.datadoghq.com/opentelemetry/setup/otlp_ingest/#intake-limits): 5.1 MiB uncompressed for logs. The smaller metrics quota applies to a different endpoint. |
| Elastic Cloud | [Managed OTLP guidance](https://www.elastic.co/docs/reference/opentelemetry/managed-inputs/managed-otlp-endpoint) recommends a 4 MB maximum batch to stay within endpoint limits. Confirm any lower intermediary limits for your deployment. |
| New Relic | [OTLP limits](https://docs.newrelic.com/docs/opentelemetry/best-practices/opentelemetry-otlp/): requests must be smaller than 1,000,000 bytes; attribute limits and asynchronous validation also apply. |
| Dynatrace | [Log ingestion limits](https://docs.dynatrace.com/docs/analyze-explore-automate/logs/lma-limits): 10 MB per request and 50,000 records, with a 16 MB post-processing ceiling. Resource/scope expansion can increase the processed size. Logs are limited to 24 hours old; select a recent export window. |
| CloudWatch Logs | The [OTLP endpoint](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/CloudWatch-OTLPEndpoint.html) has a standard 1,048,576-byte request budget calculated after decoding, with separate 16 KB resource/scope and timestamp limits. These small decision records use the standard binary-protobuf path. |
| OpenSearch Ingestion / Data Prepper | The [ingestion source](https://docs.aws.amazon.com/opensearch-service/latest/developerguide/configure-client-otel.html) defaults `max_request_length` to 10 MB; AWS allows up to 20 MB. [Self-managed Data Prepper](https://docs.opensearch.org/latest/data-prepper/pipelines/configuration/sources/otel-logs-source/) also defaults to 10 MB. Match your pipeline's configured budget. |

To use a lower request budget with `demo/export.py`, set
`WATCHER_EXPORT_MAX_REQUEST_BYTES` to a positive byte count, for example
`200000`. In application code, pass `max_request_bytes` to `OtlpLogSink`.

## Use in your application

```python
import httpx
from watcher_sdk import AsyncWatcherClient
from watcher_opentelemetry import OtlpLogSink, export_window

async with AsyncWatcherClient(watcher_url, api_key=watcher_key) as watcher:
    async with httpx.AsyncClient(timeout=30, trust_env=False) as receiver:
        receipt = await export_window(
            watcher,
            OtlpLogSink(receiver, "http://127.0.0.1:4318/v1/logs"),
            start=start_datetime,
            end=end_datetime,
        )
```

The adapter uses official OTLP protobuf messages, fetches all bounded source
pages before sending and checks each receiver response. Direct remote receiver
URLs must use HTTPS; loopback HTTP is allowed for a local Collector. The exporter
checks every encoded batch before transmitting the first. If a batch exceeds
`max_request_bytes`, lower `batch_size` or configure a suitable byte limit. The default source batch contains 100 decision records.

## Delivery and coverage limits

| Area | Behavior |
| --- | --- |
| Source coverage | The decision export reads recorded tool calls; the session export reads selected sessions and optionally their trajectories. Neither sees activity absent from Watcher. |
| Time window | Inclusive occurrence-time boundaries; adjacent windows can overlap. |
| Changing records | Offset pages are not a snapshot or change cursor. Late arrivals and later decisions require re-exporting older windows; some page inconsistencies are detected, but missing records cannot be ruled out. |
| Duplicates | Replays and ambiguous delivery can duplicate logs. Stable IDs and payload fingerprints support downstream deduplication; delivery is not exactly once. |
| Source retries | HTTP 429, 502, 503 and 504 are retried within a finite budget. Authentication errors, malformed responses, partial success and transport timeouts fail visibly at the direct receiver. |
| Collector forwarding | Destination configurations disable queueing and batch aggregation. Transient downstream failures get a bounded retry. Permanent rejection propagates to the sender; a source receipt still does not prove indexing. |
| Downstream partial success | The standard Collector logs a vendor's partial-success warning but can acknowledge upstream success. Monitor its logs and query the destination; the source receipt cannot identify downstream rejected records. |
| Partial runs | Earlier batches can be accepted before a later failure. No automatic watermark is advanced. |
| Restarts | No durable Collector queue is configured. For production, choose buffering, replay and reconciliation explicitly; adding a queue changes acknowledgment semantics. |

No destination example establishes a complete security audit trail. Alerting and
SIEM detections require destination-specific rules and their own verification.

## Tests and directory layout

```sh
uv run pytest
bash tests/native/run.sh
bash tests/native/run-services.sh
```

The ordinary Python suite uses the public Watcher SDK and loopback HTTP fixtures.
Its preparation check needs POSIX, Bash, `/bin/sh` and basic file utilities; it is
skipped when those prerequisites are unavailable.

`run.sh` requires Linux x86-64, Docker, uv and curl. It installs dependencies and
downloads a checksum-verified Collector release before disabling networking for
all runtime tests. It checks installed SDK identity, protobuf fields, pagination,
request-size boundaries, retries, authentication headers, cryptographic AWS
signatures, permanent rejection and partial-success behavior. Artifacts include
raw protobuf requests, response receipts and Collector logs.

`run-services.sh` also downloads pinned Loki, Data Prepper and OpenSearch images,
then runs the two destination stacks sequentially with memory/CPU limits.
The pinned service versions are Loki 3.5.5, Data Prepper 2.11.0 and OpenSearch
2.19.3. Each
stack shares a network-disabled namespace with its test process; no ports are
published. It reads a local Watcher source through the public SDK, exports through the
real Collector, queries indexed records and saves the raw results. This takes
several minutes and uses about 3 GB of memory for the OpenSearch stack. It proves
local storage/query behavior, not hosted accounts, IAM or security detections.

`run.sh` exercises the installed SDK and Collector protocol fixtures. The optional
service recipe saves separate raw query results, server versions and pinned image
receipts. Check those artifacts when verifying a run; local results do not
establish hosted-vendor verification.

Both scripts print their artifact directories. `WATCHER_SDK_WHEEL` can supply a
built SDK wheel; otherwise the adjacent SDK is built. `run-services.sh` normally
runs the complete preparation check first. Set `WATCHER_OTLP_FIXTURE_IMAGE` to
an image produced by `run.sh` to reuse that prepared fixture during development.

`src/watcher_opentelemetry/` is the installable exporter; `demo/export.py` is the
entry point; `config/` holds destination configurations; `tests/` contains
synthetic protocol fixtures and local service checks. `metadata.yaml` records
the verification level and dependency information. The package manifest uses
the adjacent SDK checkout for local development.

## Session summaries and transcripts

Use the same destination settings with `demo/export_sessions.py` to export
session summaries in the selected activity window. The default includes high and
critical scores, plus sessions with recorded human or automatic denials or
observe-mode deny/escalate judgments even when no score is available. Summaries
contain IDs, timestamps, counts,
scores and permission-decision counts; user fields and transcript text are omitted.

```sh
uv run python demo/export_sessions.py
```

To include every stored trajectory for those sessions, explicitly enable content:

```sh
WATCHER_EXPORT_INCLUDE_TRANSCRIPTS=true uv run python demo/export_sessions.py
```

This includes message text, tool arguments, results, grades and trajectory
metadata from the SDK's extended view. Watcher's existing content scrubbing
still applies. Check the destination's data access and retention settings for
the content you choose to export.

The Python `export_sessions` function accepts `severities=[]` for all sessions,
or a list of exact Watcher severity buckets. Session windows select overlapping
activity, so a selected session may start before or end after the window.
Exports are bounded to 100 trajectories per session and 32 MiB of source data
by default; narrow the window or deliberately change those bounds for larger
exports. Destination request limits still apply, and oversized records fail
before transmission rather than being truncated.

Session and trajectory records use `session_summary` and `transcript` record
types. Their timestamps are the session's latest activity or the trajectory's
last message time. Stable IDs and content fingerprints support reconciliation;
these snapshots are not an immutable change feed or an exactly-once delivery
system. Late arrivals and later grades require re-exporting earlier windows.

The SDK does not expose a delivered-notification feed. Configure alert rules in
your destination for notifications based on exported Watcher records; this
example does not claim to reproduce Watcher's notification delivery history.

Session and transcript payloads are JSON in the OTLP log body, with IDs and the
record type in `watcher.*` attributes. The same Collector configurations apply.

Session selection uses the highest live-tool score or latest deep-review score:
low below 4, medium 4–6, high 7–8, and critical 9–10. By default, it also includes
sessions with recorded human or automatic denials, or observe-mode judgments to
deny or escalate, even when no severity score exists. These outcomes retain their
original counts and scores; a denial does not imply a numeric severity.
Passing an explicit `severities` list filters only scores; `[]` selects all
sessions. A prior high-scoring tool can still select a session after a later
deep review gives it a lower score.
The example scans all accessible sessions in the requested activity window and
filters locally; narrow the window if the page limit is reached.
