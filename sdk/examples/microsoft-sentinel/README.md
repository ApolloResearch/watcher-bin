# Microsoft Sentinel

Export Watcher decisions, session summaries and optional transcripts to an Azure
Monitor Log Analytics custom table that you can query from Microsoft Sentinel.
The default decision export contains the tool-call ID,
session ID, occurrence time, severity when available, coverage state and decision
category. Transcript content, tool arguments, tool names and user identity are
excluded. Watcher's policy severity scores run from 1 to 10, with higher values
more severe. The example forwards the SDK's integer unchanged and keeps severity
null for unscored records.

This is an experimental example you can adapt. It exports existing records;
it does not monitor agents synchronously or create Sentinel alerts, incidents,
analytics rules or ASIM-normalized security content.

## Azure prerequisites

Configure these resources in your Azure environment before sending data:

1. A Log Analytics workspace and custom table named `WatcherDecisions_CL`.
2. A Data Collection Rule (DCR) with input stream `Custom-WatcherDecisions`, an
   identity transformation (`source`) and output `Custom-WatcherDecisions_CL`.
3. A principal with **Monitoring Metrics Publisher** on that DCR and an access
   token for the Azure Monitor audience.

The package contains matching templates at
`src/watcher_microsoft_sentinel/config/table.json` and `config/dcr.json` in the
same package directory. Replace the workspace resource ID and region placeholders
before using them in your Azure provisioning workflow. The DCR region matches the
workspace region. These are resource bodies, not deployment commands, and the
example creates no cloud resources. Review the table's retention settings before
provisioning it.

Use the DCR's `properties.endpoints.logsIngestion` origin and its immutable
`dcr-*` ID. A DCR with `kind: Direct` can provide this endpoint; an older DCR or
private-link deployment may instead require an associated Data Collection
Endpoint (DCE). The URL is neither an Azure Resource Manager URL nor a workspace
ID. The input stream name and the destination table name serve different roles.

See the [Logs Ingestion setup guide](https://learn.microsoft.com/en-us/azure/azure-monitor/logs/logs-ingestion-api-overview)
for DCR/DCE requirements, permissions and supported Azure clouds.

## Install and run

Use Python 3.12 or later and [uv](https://docs.astral.sh/uv/). From this directory
in the SDK source checkout:

```sh
uv sync
export WATCHER_URL='https://your-watcher-server/api'
export WATCHER_API_KEY='your-watcher-api-key'
export WATCHER_EXPORT_START='2026-09-01T00:00:00+00:00'
export WATCHER_EXPORT_END='2026-09-02T00:00:00+00:00'
export AZURE_LOGS_ENDPOINT='https://your-endpoint.ingest.monitor.azure.com'
export AZURE_DCR_IMMUTABLE_ID='dcr-your-immutable-id'
export AZURE_DCR_STREAM='Custom-WatcherDecisions'
export AZURE_MONITOR_TOKEN='your-monitor-access-token'
uv run python demo/export.py
```

Replace `dcr-your-immutable-id` with the actual immutable ID from the DCR. The
Watcher key needs permission to search decisions. For Azure public cloud the
token audience is `https://monitor.azure.com`; an OAuth client-credentials scope
is `https://monitor.azure.com/.default`. Obtain the token through your approved
identity workflow and ensure it outlives the finite export. Sovereign clouds use
their own Monitor audience and endpoint. The adapter does not discover machine
credentials, request a token, refresh it, or fall back to another identity.

The command reports accepted row counts after every request returns HTTP 204.
This confirms ingestion-request acceptance, not searchable rows. In the workspace,
set the time picker to a range covering **both the original occurrence window and
the time you run the export**. After a recent run, query:

```kusto
WatcherDecisions_CL
| where ingestion_time() > ago(1h)
| summarize arg_max(ingestion_time(), *) by RecordFingerprint
| project TimeGenerated, OccurredAt, ToolCallId, SessionId, CoverageState, DecisionCategory, SeverityScore
```

Azure Monitor [replaces `TimeGenerated`](https://learn.microsoft.com/en-us/azure/azure-monitor/logs/log-standard-columns#timegenerated)
with the received time when the supplied timestamp is more than two days old or
more than one day in the future. The separate `OccurredAt` column retains the
original Watcher timestamp. Use that column for occurrence-time queries. Selecting
only an old source window in the portal can hide a successful historical import;
selecting only the export time can hide recent records whose timestamp stays
unchanged. Hosted timestamp rewriting is not exercised by the local fixture.

`RecordFingerprint` identifies the exported field version and permits query-side
deduplication. The request ID is for diagnostics, not idempotency. Build and test
Sentinel analytics rules separately after validating the resulting table.

## Use in your application

```python
import httpx
from watcher_sdk import AsyncWatcherClient
from watcher_microsoft_sentinel import LogsIngestionSink, export_window

async with (
    AsyncWatcherClient(watcher_url, api_key=watcher_key) as watcher,
    httpx.AsyncClient(timeout=30, trust_env=False) as http,
):
    receipt = await export_window(
        watcher,
        LogsIngestionSink(http, logs_endpoint, monitor_token, rule_id=dcr_id),
        start=start_time,
        end=end_time,
    )
```

Use timezone-aware `datetime` values. The adapter calls Logs Ingestion API
`2023-01-01` with a UTF-8 JSON array. That is an API schema version, not an observed
Azure service release. Null severity or decision values remain null; the example
does not fabricate an allow or deny result.

Default source bounds are 100 pages of 200 records. Default destination bounds
are 100 rows or 900,000 encoded bytes per request, below Azure's 1 MB request
limit. Set `page_size`, `max_pages`, `batch_size` or `max_batch_bytes` on
`export_window` to change these bounds; the byte cap cannot exceed 1,000,000.
The example's UUIDs, fixed classifications and timestamps fit below Azure's
64 KB field limit. It validates all source records before destination writes.

## Delivery and testing limits

The source window is inclusive at both ends. Offset pagination and
occurrence-time filters do not expose snapshot isolation or a decision-change
cursor. The adapter refuses observed count changes, duplicate IDs,
out-of-window records and time-order regressions, but same-size concurrent
changes can escape detection. Reconcile late arrivals and decisions updated
outside the window separately; this is not a complete audit feed.

HTTP 429/500/502/503/504 have up to three attempts. `Retry-After` values up to
30 seconds are honored; a longer delay stops the finite export so you can
reconcile and retry later. Authentication errors, redirects, unexpected responses and
transport errors stop delivery. No token refresh occurs on HTTP 401. Retries,
replays and ambiguous delivery can duplicate rows. Earlier batches may already
be accepted when a later batch fails. Changed classifications produce new
fingerprints and do not delete the old rows. The example keeps no durable
checkpoint and does not guarantee exactly-once delivery.

Run the complete local check with Docker and uv:

```sh
bash tests/native/run.sh
```

Dependencies are downloaded while the image is prepared. Runtime tests use
`--network none`, the real installed public Watcher SDK, and loopback HTTP
fixtures for Watcher and Azure ingestion. Only an injected dummy token is used.
Tests cover the actual serialized URL, stream, headers, schema, null fields,
pagination, byte limits, retries, partial progress and malformed responses.
This establishes local **protocol-contract coverage**. It does not verify Azure
permissions, DCR transformations, table indexing, Sentinel detections or a deployed
Watcher server. `metadata.yaml` records this scope and observed versions.

`src/watcher_microsoft_sentinel/` contains the installable adapter and configuration
assets. `demo/export.py` is the entry point; `tests/` holds the behavioral fixtures.
`pyproject.toml` and `uv.lock` use the adjacent SDK during development.
`uv build --wheel` produces an independent example wheel with a public
`watcher-sdk` dependency.

References: [request and authentication contract](https://learn.microsoft.com/en-us/azure/azure-monitor/logs/logs-ingestion-api-overview),
[REST example and response status](https://learn.microsoft.com/en-us/azure/azure-monitor/logs/tutorial-logs-ingestion-code),
[request and field limits](https://learn.microsoft.com/en-us/azure/azure-monitor/fundamentals/service-limits#logs-ingestion-api).

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

Use the packaged table and DCR schemas, including `RecordType`, `TrajectoryId`
and the dynamic `Snapshot` column. Update an existing example table/DCR to include
those columns before exporting sessions. Filter `RecordType` to select a record
class; the `Snapshot` column contains its public Watcher fields.

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
