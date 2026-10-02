# Google Security Operations

Export Watcher tool-call decisions, session summaries and optional transcripts
to Google Security Operations through
the **Chronicle v1 `events:import` API**. This Python example reads a finite time
window through the public Watcher SDK and sends Unified Data Model (UDM)
events. The default decision export excludes transcript content. It is an experimental example you can install and adapt.

The local tests exercise the real Watcher SDK and HTTP requests against isolated
fixtures. **Google-hosted UDM acceptance, indexing, IAM access and detection rules
are not verified.** A successful local run checks the adapter's request contract;
it does not establish a working Google SecOps tenant.

## What it exports

Each decision record becomes a `GENERIC_EVENT` with these fields:

| UDM field | Value |
| --- | --- |
| `metadata.eventTimestamp` | The Watcher tool call's occurrence time, not a decision update time. |
| `metadata.vendorName` / `productName` | `Apollo Research` / `Watcher`. |
| `metadata.productEventType` | `tool_call_decision`. |
| `metadata.productLogId` | The Watcher tool-call UUID. |
| `additional` | Tool-call and session UUIDs, a fingerprint of the exported fields, coverage/content states and, when present, the Watcher decision category and severity score. |

The mapping uses the UDM `additional` object for vendor-specific fields. Watcher
severity is **not** converted to Google severity. Current Watcher policy scores
use a 1–10 scale. The exporter forwards source integers unchanged, without
rescaling or clamping, and omits the score when the source is unscored.
Observation-mode categories such as `would_denied` remain source values; they do
not claim an action was blocked.
No user, machine, process, principal, target or Google event ID is invented.
Transcripts, tool names, arguments, summaries, user identities and message
references are excluded. Exported UUIDs remain correlatable identifiers; give the
destination appropriate access and retention controls.

Direct UDM import does not need a raw-log type or custom parser. It does require
Google to accept the UDM mapping. The distinct `logs:import` API accepts raw logs
under a log type and requires an appropriate parser; this example does not use it.
Neither path automatically creates a SIEM detection or synchronously blocks tools.

## Install

Use Python 3.12 or newer and run these commands from this directory:

```sh
uv sync --frozen
```

The source checkout resolves `watcher-sdk` from `../..`. To install the example
outside this checkout, build its wheel and install it alongside your supported
Watcher SDK distribution:

```sh
uv build --wheel
python -m pip install dist/watcher_google_security_operations_example-0.1.0-py3-none-any.whl
```

The wheel uses the normal `watcher-sdk>=0.1,<1` dependency and has no imports from
Watcher server code or other example packages. `uv.lock` pins the checkout's test
environment; it does not establish compatibility with every permitted SDK release.

## Configure and export

You need an onboarded Google SecOps instance and its Google Cloud project,
location and instance ID. Enable/configure the Chronicle API for that instance.
Use the regional endpoint listed for its location, such as
`https://us-chronicle.googleapis.com`.

Have your IAM administrator grant **`chronicle.events.import`** for the target
instance. Google's predefined `roles/chronicle.editor` includes this permission
but grants broader access; a suitably scoped custom role can limit it. Supply a
short-lived OAuth access token with either the
`https://www.googleapis.com/auth/cloud-platform` or
`https://www.googleapis.com/auth/chronicle` scope. API keys are not supported by
this import method. See Google's [authentication guide](https://docs.cloud.google.com/chronicle/docs/reference/authentication)
for obtaining a token using your organization's approved identity setup.

Set these environment variables in the process running the export. Values below
are placeholders; keep credentials out of source control and shell history.

```sh
export WATCHER_URL='https://your-watcher-server/api'
export WATCHER_API_KEY='your-watcher-api-key'
export WATCHER_EXPORT_START='2026-01-01T00:00:00Z'
export WATCHER_EXPORT_END='2026-01-02T00:00:00Z'
export GOOGLE_SECOPS_ENDPOINT='https://us-chronicle.googleapis.com'
export GOOGLE_SECOPS_PARENT='projects/your-project/locations/us/instances/your-instance-id'
export GOOGLE_SECOPS_ACCESS_TOKEN='your-short-lived-oauth-token'
uv run --frozen python demo/export.py
```

The demo discovers no ambient Google credentials and does not refresh expired
tokens. A `401` or `403` stops the run. Its output reports only HTTP-acknowledged
record and batch counts. For use in another application, import
`GoogleSecOpsSink` and `export_window` from `watcher_google_security_operations`;
the demo shows client lifetimes and configuration.

The default batches contain at most 100 records with a one-MiB JSON request bound.
This is an example safety bound, not a statement of Google's ingestion quota.
`export_window(..., batch_size=...)` can lower it. All source pages and request
sizes are checked before the first destination write. A malformed source page,
changed total, duplicate tool-call ID or out-of-window record stops the export.

## Delivery and source limits

The API documents rejection of the whole request when any event is invalid. The
adapter requires HTTP 200 with an empty response or empty JSON object; unexpected
partial results, warnings or response shapes fail. For explicit HTTP 429 responses,
it makes at most three attempts (two retries), respecting bounded `Retry-After` delays. It does
not retry redirects, transport failures or server errors, since acceptance can
be ambiguous. Receiver response bodies and tokens are excluded from its errors.

An earlier batch can be accepted before a later failure. `ExportError` exposes
`acknowledged_records` and `acknowledged_batches` for that invocation. Those counts
are not a safe resume cursor: reconcile destination records before replaying a
failed window. The tool-call UUID and fingerprint can help compare records, but
neither guarantees destination deduplication.

Watcher search uses inclusive occurrence-time filters and offset pagination.
It provides no immutable snapshot or mutation cursor. Adjacent windows can repeat
boundary records, while late arrivals and changed decisions require reconciliation.
Only tool calls that entered Watcher's decision path appear. This exporter is not
a complete audit feed and does not import general Google telemetry into Watcher.

## Test locally

From the repository root, with Docker and uv installed:

```sh
bash product/sdk/examples/google-security-operations/tests/native/run.sh
```

Preparation downloads packages and builds wheels. All runtime tests then execute
inside a Docker container with `--network none`, fake credentials, and loopback
Watcher/Chronicle fixtures. The run installs the SDK wheel, checks its installed
bytes, exercises HTTP serialization and retains JUnit results plus container and
SDK identity under the printed artifact directory. It never contacts Google.

Tests cover source pagination and consistency, privacy, JSON field mappings,
Google's protobuf `Timestamp` and `Struct` types, size bounds, acknowledgment
validation, retries, redirects, transport failures and partial multi-batch progress.
These are **documented HTTP contract tests**, not a local Google server or a
complete UDM semantic validator.

Before operational use, an authorized operator must submit a small synthetic
window to their tenant, confirm UDM search finds `metadata.product_name = "Watcher"`
with matching product-log IDs and additional fields, then independently verify any
customer detection rules. Search and detection setup need permissions beyond
`chronicle.events.import`. No hosted test runs automatically.

## API references

- [Chronicle v1 events.import](https://docs.cloud.google.com/chronicle/docs/reference/rest/v1/projects.locations.instances.events/import): endpoint, all-or-nothing validation, response and OAuth/IAM requirements.
- [Event resource](https://docs.cloud.google.com/chronicle/docs/reference/rest/v1/projects.locations.instances.events): `Event.udm` envelope.
- [UDM REST schema](https://docs.cloud.google.com/chronicle/docs/reference/rest/Shared.Types/Collection#UDM): lowerCamelCase REST fields and `additional` Struct.
- [UDM usage](https://docs.cloud.google.com/chronicle/docs/unified-data-model/udm-usage): required timestamps/types and uncategorized events.
- [Regional endpoints](https://docs.cloud.google.com/chronicle/docs/reference/rest#rest_endpoints) and [IAM roles](https://docs.cloud.google.com/iam/docs/roles-permissions/chronicle).

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

Session and transcript exports remain `GENERIC_EVENT` records, with their
`productEventType` identifying the record class and `additional.watcher_snapshot`
carrying the public Watcher payload. They are not Google detections or alerts.

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
