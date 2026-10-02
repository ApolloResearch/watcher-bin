# Splunk

Export Watcher tool-call decisions, session summaries and optional transcripts
to Splunk's HTTP Event Collector (HEC). The default decision export contains the tool-call ID, session ID, occurrence time, severity
when available, coverage state and decision category. Transcript text, tool
arguments, tool names and user identity are excluded. Watcher's policy severity
scores run from 1 to 10, with higher values more severe. The example forwards the
SDK's integer unchanged and omits severity when the record is unscored.

This is an experimental example you can adapt. It exports existing records;
it does not observe new agent activity, block tools, or create Splunk detections.

## Install and configure

Use Python 3.12 or later and [uv](https://docs.astral.sh/uv/). From this directory
in the SDK source checkout:

```sh
uv sync
export WATCHER_URL='https://your-watcher-server/api'
export WATCHER_API_KEY='your-watcher-api-key'
export WATCHER_EXPORT_START='2026-09-01T00:00:00+00:00'
export WATCHER_EXPORT_END='2026-09-02T00:00:00+00:00'
export SPLUNK_HEC_ORIGIN='https://your-hec-host:8088'
export SPLUNK_HEC_TOKEN='your-hec-token'
export SPLUNK_INDEX='watcher'
uv run python demo/export.py
```

The Watcher key needs permission to search tool-call decisions. Enable HEC on
your Splunk deployment and create a token authorized for the destination index.
Use its HTTPS **origin**, without `/services/collector/event`; the adapter adds
that path. Splunk Cloud and Enterprise use different hostnames and sometimes
ports: use the endpoint supplied by your administrator. If `SPLUNK_INDEX` is
unset, HEC uses the token's default index. Supply credentials through your usual
secret-management mechanism. The command sends records to the configured HEC.

A successful command reports counts accepted by HEC. Search the selected index
and time range to verify indexing:

```spl
index=watcher sourcetype="watcher:decision"
| spath
| dedup record_fingerprint
| table _time tool_call_id session_id coverage_state decision_category severity_score
```

The query is a starting point, not a configured alert or Splunk security content
pack. `record_fingerprint` identifies the exported field version. It is not an
HEC idempotency key, so deduplication is a query-side operation.

## Optional Enterprise acknowledgments

For an **Enterprise HEC token with indexer acknowledgment enabled**, set
`SPLUNK_HEC_ACK=true`. The sender includes a UUID request channel, validates the
returned `ackId` or `ackID` (an integer or decimal digit string), and polls
`/services/collector/ack`. Conflicting IDs stop delivery rather than choosing one.
Ordinary Splunk Cloud HEC
clients do not support this acknowledgment flow; Splunk documents a separate
exception for AWS Kinesis Firehose.

A true acknowledgment confirms the requested replication factor. It does **not**
guarantee searchable indexing: parsing can still drop events. False can mean
pending, unknown or expired. A true acknowledgment is consumed when queried,
so retain successful results and do not poll it again.

Library callers can retain `AcknowledgmentPending.channel` and `.ack_id`, create
a new `HecSink` with that same channel and call `await sink.wait_for_ack(ack_id)`
without resending the events. The demo has no durable polling checkpoint; a
process crash or lost response can leave delivery uncertain.

## Use in your application

```python
import httpx
from watcher_sdk import AsyncWatcherClient
from watcher_splunk import HecSink, export_window

async with (
    AsyncWatcherClient(watcher_url, api_key=watcher_key) as watcher,
    httpx.AsyncClient(timeout=30, trust_env=False) as http,
):
    receipt = await export_window(
        watcher,
        HecSink(http, hec_origin, hec_token, index="watcher"),
        start=start_time,
        end=end_time,
    )
```

Use timezone-aware `datetime` values. The library reads and validates the whole
window before destination writes. Defaults limit reads to 100 pages of 200
records and batches to 100 events or 900,000 encoded bytes. Set `page_size`,
`max_pages`, `batch_size` or `max_batch_bytes` on `export_window` when needed;
the example caps the last setting at 1,000,000 bytes. Splunk deployment limits
can be smaller. A single event exceeding the configured cap fails before delivery.

## Delivery and testing limits

Both window boundaries are inclusive. Adjacent windows, reruns and retries can
duplicate events. Offset pagination and occurrence-time filters provide neither
snapshot isolation nor a decision-change cursor. Late arrivals and updates to
older decisions require reconciliation; this example is not a complete audit
feed. It refuses observed count changes, duplicate IDs, out-of-window records
and time-order regressions, but same-size concurrent changes can escape detection.

Only HTTP 200 with HEC body code zero counts as acceptance. Queue-at-capacity
responses (HTTP 429 with code 26/27) and server-busy responses (503 with code 9)
have up to three attempts. `Retry-After` values up to 30 seconds are honored;
a longer delay stops the finite export so you can reconcile and retry later.
Other body codes, redirects,
malformed acknowledgments and transport errors stop delivery. Even an error may
follow accepted events. Earlier batches remain accepted when a later one fails;
replaying without reconciliation can duplicate them. A fingerprint changes when
an exported classification changes; it does not retract older events.

Run the complete local check with Docker and uv:

```sh
bash tests/native/run.sh
```

Dependencies are downloaded while the image is prepared. Tests then run inside
`--network none` with a real installed public Watcher SDK and loopback HTTP
fixtures for Watcher and HEC. They cover pagination, serialization, privacy,
byte limits, response errors, retries and acknowledgment polling. This is local
**protocol-contract coverage**, not a running Splunk deployment. It does not
verify token permissions, hosted indexing, search extraction or detection rules.
`metadata.yaml` records the actual verification level and observed versions;
no Splunk server version is inferred from these fixtures.

`src/watcher_splunk/` is the installable package, `demo/export.py` is the entry
point, and `tests/` contains the behavioral fixtures. `pyproject.toml` and
`uv.lock` use the adjacent SDK for development. `uv build --wheel` produces an
independent example wheel whose runtime dependency is the public `watcher-sdk`.

Protocol references: [HEC event format](https://help.splunk.com/en/splunk-enterprise/get-started/get-data-in/9.4/get-data-with-http-event-collector/format-events-for-http-event-collector),
[response codes](https://help.splunk.com/en/splunk-enterprise/get-started/get-data-in/9.4/get-data-with-http-event-collector/troubleshoot-http-event-collector),
[acknowledgment semantics](https://help.splunk.com/en/splunk-enterprise/get-started/get-data-in/9.4/get-data-with-http-event-collector/about-http-event-collector-indexer-acknowledgment).

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

Session and transcript HEC events use sourcetypes `watcher:session_summary` and
`watcher:transcript`. Query those sourcetypes when verifying this export path.

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
