# Monitor Cohere V2 tools with Watcher

This example connects Cohere's Python `AsyncClientV2` to Watcher. The application
sends complete chat history, waits for Watcher before dispatching its own tools,
and submits tool results and the final reply through the same hook endpoint.
It is an example to adapt, not an officially supported integration.

`Monitor` inherits the server's enforcement setting. Enforce mode applies allow,
deny and human-escalation decisions. Observe and paused modes preserve ordinary
application dispatch. Provider-hosted tools and calls outside this wrapper are
outside its control.

## Install and configure

Use Python 3.12 or newer and uv. From this directory:

```sh
uv sync --python 3.12
```

The development environment uses the adjacent Watcher SDK source directory.
For a released SDK wheel, follow the [shared setup guide](../README.md).
`pyproject.toml` and `uv.lock` define the package and dependencies. `uv build
--wheel` builds an installable example package.

Set `PROVIDER_API_KEY`, `PROVIDER_BASE_URL`, `PROVIDER_MODEL`, `WATCHER_API_KEY`
and `WATCHER_BASE_URL` as shown in `demo/.env.example`. The Watcher credential
needs `sessions:ingest` permission. Scripts read environment variables; they do
not load an `.env` file automatically.

Run the monitored conversation:

```sh
uv run python demo/enforce.py
```

The script uses a local demonstration weather function and then asks the model
for a final answer. It uses the server's current mode despite the script name.
Replace the function and its declaration with your application's tool. Each new
conversation needs its own `Monitor` and unique session ID. Keep the returned
native history intact between calls to `run_turn`.

The demo sends its prompt and results to the configured provider and Watcher.
A successful hook response acknowledges submission, not durable recording.
Verify the session's tool IDs, arguments, results and final answer in Watcher
before relying on the deployment for audit coverage.

## Human approval and unattended operation

Without an approval callback, escalation raises `ApprovalRequired` and no tool
in the pending batch executes. This is the unattended default.

An application can supply `Monitor(..., approval_callback=approve)`. The async
callback receives `tool_use_id`, `tool_name`, a detached copy of `tool_input`, and
`outcome`. It must await the application's authorized human interface and return
literal `True` to permit the call. All approvals finish before any tool in the
batch starts. Other return values withhold execution.

The callback is local application behavior. This example supplies no approval UI
and does not upload human choices to Watcher's decision audit. Do not interpret
its stored escalation as a record that the human approved the call.

Watcher transport failures, malformed replies and identity mismatches withhold
tools. Grading failures follow the administrator's configured allow/deny policy.
`WATCHER_TIMEOUT` changes the default 420-second request budget. An explicit
`enforcement` argument can request a mode, but locked organization settings can
reject overrides; the default sends none.

## Optional background observation

`demo/observe.py` uses a bounded background queue and inherits the server policy,
including locked and paused settings. Its results arrive after the provider call
and cannot block tools. A stored evaluation does not prove a historical tool was
prevented. Use the synchronous `Monitor` to apply decisions before dispatch.

```sh
uv run python demo/observe.py
```

Call `flush()` after producers stop and inspect `errors` and `error_count`.
The queue holds at most 32 pending snapshots, submits them in order, and reports
overflow. It has no durable spool or replay after process loss.

## Conversion and recovery

Cohere's native V2 format requires the example's converter. It preserves textual
content blocks, tool plans, tool IDs and JSON argument types. Media, documents,
citations and streaming are unsupported and fail explicitly. The converter does
not pretend a Cohere response is an OpenAI response.

`run_turn` submits completed tool results without grading them again. If that
submission fails after tools ran, it raises `RecordingFailed` with detached
`history` and `messages`. Retry `await monitor.record(error.messages)` and
continue with `error.history`; do not rerun the tools. Attempted IDs cannot be
dispatched twice by one monitor, but this is not durable exactly-once execution
across process restarts.

## Tests and layout

`src/watcher_cohere/` holds conversion, monitoring and observation code. `demo/`
contains runnable entry points. `tests/` exercises the installed Cohere client
with local provider and Watcher replies, including policy modes, pending human
approval, refusal, argument types, ordering and recovery. `metadata.yaml` records
the observed versions and actual verification scope.

Install dependencies first, then run tests without external networking:

```sh
env -i PATH="$PATH" ../run-without-network.sh "$PWD/.venv/bin/python" \
  -m pytest --confcutdir="$PWD" -c pyproject.toml tests
```

Local fixtures do not establish hosted Cohere access or model quality. Verify
provider authentication and the selected model in your own deployment.
