# Vercel AI SDK → Watcher

Monitor native `generateText` tool execution with Watcher and submit the actual
conversation. The Node tool callback waits for a Python sidecar using the public
Watcher SDK. The same integration follows the server's enforce, observe or paused
setting. This is an experimental example, not an officially supported integration.

## Install and configure

Use Python 3.12 or later, `uv` and Node 24.11.1. The Node package pins AI SDK 5.0.99;
each component has a manifest and lockfile under `packages/`. From this directory:

```sh
uv sync --project packages/python --python 3.12
mkdir -p dist
npm pack ./packages/node --pack-destination dist --ignore-scripts
npm install --no-save --package-lock=false --ignore-scripts dist/watcher-vercel-ai-example-0.1.0.tgz
export PATH="$PWD/node_modules/.bin:$PATH"
export WATCHER_PYTHON="$PWD/packages/python/.venv/bin/python"
```

Both components are required. The Python development environment uses adjacent
SDK source; follow the [shared setup guide](../README.md) for a released SDK wheel.
The installed sidecar commands do not require sibling source files.

Set `WATCHER_URL` and a session-write `WATCHER_API_KEY`. `WATCHER_TIMEOUT` selects
the grading deadline in seconds, default 420. The demo uses scripted model replies
and real native arithmetic tools, so no provider key is needed. Environment
variables are read directly; `.env` files are not loaded.

## Monitor native tools

```sh
packages/python/.venv/bin/python demo/enforce.py
```

Native `tool.execute` awaits the sidecar before the application tool body runs.
Public model middleware retains the current pending reply because it is absent
from the tool callback's messages. Original tool IDs and arguments are preserved;
the Python sidecar checks that execution matches the authorized call.

Create one `Monitor(client, conversation_id)` from
`watcher_vercel_ai_bridge.monitoring` per conversation. Pass it to
`watcher_vercel_ai_bridge.synchronous.run_conversation` for the runnable native
fixture. Reuse full history and the conversation ID across application turns.

| Watcher result | Integration behavior |
| --- | --- |
| Enforce: allow | Release native tool dispatch, including an administrator-configured allow on a grading failure. |
| Enforce: deny | Withhold the tool body and return a native tool error. |
| Enforce: escalate | Await an application approval callback if supplied; otherwise withhold execution. |
| Observe or paused: deferred | Preserve ordinary native dispatch and permission checks. |

Malformed outcomes, transport failures and mismatched identities withhold the
pending tool. `enforcement="observe"`, `"enforce"` or `"paused"` requests an explicit
override; an administrator lock may reject it. The default inherits server policy.

AI SDK may continue generating after a rejected call, retaining a native tool-error
result. That is not successful tool execution. Each fresh call receives its own
check. Requests are handled serially, so several calls may consume several grading
deadlines. Node inherits stderr to avoid a blocked unread pipe.

## Human approval

Pass an asynchronous `approval_callback` to the Python Monitor. It receives
`tool_use_id`, `tool_name`, copied `tool_input`, and the public hook `outcome`.
Connect it to an authorized person's approval UI or queue. Only an explicit bool
is accepted. The supplied demo omits this callback, so unattended escalations block.

Before releasing an approval, the monitor finds the original recorded escalation,
uploads the human choice and verifies its stored value and pending/blocked status. Original
grades and escalation remain intact. Readback prevents a successful scrub no-op
from being mistaken for a stored approval. This requires findings and content access
and permission to update the session as its owner or with `sessions:write:any`.
For a service API key, configure `sessions:ingest`, `sessions:findings:read:any`,
`sessions:content:read:any` and `sessions:write:any` for transcript recording and human-decision reporting.
Lookup, upload and readback errors block the call. `human_audit_timeout` defaults to 10 seconds. Approval is recorded as pending
execution; rejection as blocked.

This example supplies no approval UI, durable interrupt/resume mechanism or automatic
review model. Keep the process alive while waiting and persist application state
separately when recovery is required.

## Transcript submission and scope

Results and final text are submitted through the same public hook with no pending
input. The external ID is `other=vercel-ai:<conversation_id>`. Query that ID in
Watcher to verify stored messages, call IDs, decisions and linked results. Hook
success confirms request acceptance; asynchronous recording has no durability
acknowledgement. Retain native history when submission fails and retry submission,
not tool execution.

`demo/observe.py` provides a separate completed-history observer. It grades calls
using historical prefixes and attempts final-tail submission even after a grading
error. It inherits organization policy without an override, including paused
mode, which records history without grading. Decisions are advisory to completed
actions and cannot prevent or undo their effects.

In Enforce mode, Watcher can store a retrospective assessment as an applied
denial and count it in automatic-denial totals after the tool has run. Those
records describe the assessment; they do not show that execution was prevented.

Only buffered text and local function tools passing through this callback are
covered. Provider-hosted tools, other clients, unwrapped tools and other application
side effects remain outside it. The application must retain complete native history.
In-memory call-ID tracking does not guarantee exactly-once execution across restarts.

## Development and verification

```sh
bash tests/native/run.sh
```

The runner builds both example packages and the SDK, installs them outside the
checkout and runs the native AI SDK path with local model/Watcher fixtures.
Downloads finish before runtime networking is isolated. `WATCHER_SDK_WHEEL` selects
a prebuilt SDK wheel; `WATCHER_EXAMPLE_RUN_DIR` selects a parent for retained output.
The Linux wrapper requires noninteractive `sudo`, `unshare`, `setpriv` and `ip`
and stops if isolation fails.

Prepare the installed image for Watcher API/database verification with:

```sh
bash tests/native/build.sh
```

This recipe requires Linux x86_64, Python 3.12+, uv, Docker and package-registry
access. It accepts `WATCHER_SDK_WHEEL` and `WATCHER_EXAMPLE_RUN_DIR`, creates a fresh
output directory, and writes `image.id`, package checksums and source-comparison
receipts there. It prepares artifacts without starting an agent; the Watcher
backend runner launches the image separately with networking disabled.

The build uses a checksum-verified Node 24.11.1 archive and the committed npm
lockfile. Package lifecycle scripts are disabled during installation.

Tests check actual tool effects, pending and rejected decisions, configured modes,
human reporting, identity matching, native errors and final transcripts. Fixture
Watcher responses alone do not prove real server persistence or grade quality.
`metadata.yaml` records tested versions and scope; [the metadata guide](../METADATA.md)
explains those fields. Runtime source is under `packages/`, runnable clients under
`demo/`, and checks under `tests/`.
