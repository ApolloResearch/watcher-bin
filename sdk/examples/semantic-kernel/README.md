# Semantic Kernel → Watcher

Use `watcher_semantic_kernel` to monitor native tool calls through the public Watcher SDK
and submit their conversation to Watcher. The same before-tool integration follows
the server's configured enforcement mode. This is an experimental example, not an
officially supported integration.

## Install and configure

Use Python 3.12 or later and `uv`. The pinned framework packages are `semantic-kernel==1.37.0`, `azure-ai-agents==1.2.0b6`.
From this example directory:

```bash
uv sync --python 3.12
```

The development environment uses the adjacent SDK source. To install with a
released SDK wheel, follow the [shared setup guide](../README.md), then install
this package with `uv pip install --python /path/to/application/.venv/bin/python .`.

Set `WATCHER_URL` and a `WATCHER_API_KEY` with session-write permission using the
names in `demo/.env.example`. The demos read environment variables directly and
do not load `.env` files. Their scripted model and arithmetic tools need no model
API key. `WATCHER_TIMEOUT` sets the demo's grading deadline in seconds, default 420.

## Monitor native tools

Create one `Monitor(client, conversation_id)` per conversation. Reuse its ID across
turns and choose a new ID for an independent conversation. Register `WatcherFilter(monitor)` as an automatic function invocation filter before running `ChatCompletionAgent`. It awaits Watcher before calling the kernel continuation. Direct application calls to `kernel.invoke` do not pass through this filter.

```python
from watcher_semantic_kernel import Monitor

monitor = Monitor(client, conversation_id)
from semantic_kernel.filters import FilterTypes
from watcher_semantic_kernel import WatcherFilter

kernel.add_filter(FilterTypes.AUTO_FUNCTION_INVOCATION, WatcherFilter(monitor))
```

The complete registration and native runner are in `demo/enforce.py`:

```bash
.venv/bin/python -m demo.enforce
```

Watcher controls the policy; the integration applies its returned decision:

| Server result | Example behavior |
| --- | --- |
| Enforce: allow | Resume the framework's normal tool dispatch. This also honors an administrator's configured allow on a grading failure. |
| Enforce: deny | Raise `ToolBlocked` before the tool body executes. |
| Enforce: escalate | Wait for the supplied human-approval callback, or raise `ApprovalRequired` if no callback is configured. |
| Observe: deferred | Preserve the framework's ordinary dispatch and permissions; Watcher's judgment does not block the call. |
| Paused: deferred | Preserve ordinary dispatch and permissions; Watcher submits the transcript without grading. |

A network error, malformed response or mismatched call ID never grants permission.
The example does not disable another tool or framework permission check.

The default inherits organization policy. To request an explicit permitted mode,
use `Monitor(client, conversation_id, enforcement="observe")` (or `"enforce"` or
`"paused"`). An administrator lock can reject the override, even if it repeats the
current value. `mode="auto"` is not a hook setting.

## Human approval and unattended use

For an unattended agent, omit `approval_callback`: allowed calls execute, while
denials and human escalations stop the affected call. This does not run a separate
automatic approval model or recreate Watcher Live's Auto Mode.

For a human in the loop, supply an asynchronous `approval_callback` to `Monitor`.
The callback receives keyword arguments `tool_use_id`, `tool_name`, `tool_input`
and `outcome` (the SDK's hook response). Connect it to your application's approval
UI or queue and await an authorized person's decision. Only literal `True`
releases the still-pending call; false values, exceptions and callback failure
withhold it. The example does not include an approval UI. Tool arguments passed
to the callback are a copy, so editing the approval view cannot rewrite execution.

This callback is attached to the real framework execution boundary. It is not a
native persistent interrupt/resume implementation. Keep the process alive while
waiting, and persist application state separately if approvals must survive restarts.

After an explicit human choice, the integration waits for the original escalation
in Watcher, uploads an outcome-only decision, and reads back the stored human
choice and tool status. Only then can an approved tool execute. Original grades
and escalation remain intact; approval is recorded as pending execution,
rejection as blocked.
This requires session-read access and permission to update the session as its
owner or with `sessions:write:any`.
For a service API key, configure `sessions:ingest`, `sessions:read:any` and
`sessions:write:any` for transcript recording and human-decision reporting.
Lookup, permission, upload, content-scrub or readback failures block execution. The default reporting deadline is 10 seconds; configure
`human_audit_timeout` to change it. Recent human decisions accompany later grading
requests as context. Persist the human choice in your application if recovery is
needed; the example does not retry tools after a reporting failure.

## Submit results and inspect Watcher

After a turn, call `await monitor.record(native_history)` with the tool results
and final assistant answer. This uses the same hook with no pending input, so it
does not regrade old calls. If submission fails, retain the history and retry the
submission rather than executing the tools again.

The session's external ID is `other=semantic-kernel:<conversation_id>`. Query that ID in
Watcher to confirm the transcript and decisions. A successful hook response
confirms evaluation or request acceptance; transcript/decision storage runs after
the response and has no durability acknowledgement. Session-write permission is
required for recording even when the policy decision itself succeeds.

You can also observe a conversation that already completed using
`await observe(client, conversation_id, native_history)` or `python -m demo.observe`.
That separate import path follows the organization's policy without an override,
assesses calls against their historical prefixes in batches of at most 32, and
submits the final transcript. Paused mode records history without grading.
Returned decisions are advisory to completed actions; they cannot prevent or
undo an effect, and the importer does not report an action as blocked.

When this retrospective observer runs against an organization in Enforce mode,
Watcher can store an assessment as an applied denial and count it in automatic
denial totals after the tool has run. Those records describe the assessment;
they do not show that execution was prevented.

## Scope and limitations

Text and native FunctionCallContent/FunctionResultContent are supported. Plugin-qualified names and native call IDs remain intact. The automatic filter receives the model history, including configured agent instructions; include those instructions when retaining and submitting the final conversation too. Later filters must not rewrite already authorized arguments.

Only registered tools passing through the documented boundary are monitored.
Unwrapped tools, provider-hosted tools and other application side effects remain
outside it. In parallel work, an allowed sibling may finish while another call
is blocked. Completed effects are not undone. A failed run may have no final-tail
submission; the caller should retain and submit the native history it can recover.

A Monitor never retries tool execution or grading automatically. Failed attempts
consume their call IDs within that Monitor; a new model invocation needs its own
ID and transcript entry. This in-memory protection is not durable exactly-once
execution. Grading may finish after the caller times out and can still incur usage.

## Development and verification

`src/` contains the adapter; `demo/` contains runnable native clients; `tests/`
checks conversion, policy handling and native side effects. Tests use the installed
framework with a scripted model and fixture Watcher responses, including an awaited
approval/rejection event. Those tests alone do not establish real server persistence.
Human-outcome persistence requires the separate real-backend verification.
See `metadata.yaml` for recorded versions and verification scope.

Run the development suite from this directory with outbound networking disabled:

```bash
env -i PATH="$PATH" ../run-without-network.sh env \
  PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONDONTWRITEBYTECODE=1 \
  OTEL_SDK_DISABLED=true LANGCHAIN_TRACING_V2=false LANGSMITH_TRACING=false \
  "$PWD/.venv/bin/python" -m pytest -p pytest_asyncio.plugin \
  --noconftest -c pyproject.toml tests -q
```

The Linux wrapper requires permission to create a network namespace and stops if
isolation fails. The [metadata guide](../METADATA.md) explains verification fields.
