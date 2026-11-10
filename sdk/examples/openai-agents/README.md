# OpenAI Agents SDK → Watcher

Use `watcher_openai_agents` to monitor native tool calls through the public Watcher SDK
and submit their conversation to Watcher. The same before-tool integration follows
the server's configured enforcement mode. This is an experimental example, not an
officially supported integration.

## Install and configure

Use Python 3.12 or later and `uv`. The pinned framework packages are `openai-agents==0.4.2`.
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
turns and choose a new ID for an independent conversation. Pass `WatcherHooks(monitor)` to `Runner.run(..., hooks=...)`. The native lifecycle hook holds each local FunctionTool before its body runs and captures model input/output for the transcript.

```python
from watcher_openai_agents import Monitor

monitor = Monitor(client, conversation_id)
from watcher_openai_agents import WatcherHooks

hooks = WatcherHooks(monitor)
result = await Runner.run(agent, prompt, hooks=hooks)
```

The complete registration and native runner are in `demo/enforce.py`:

```bash
.venv/bin/python -m demo.enforce
```

Watcher controls the policy; the integration applies its returned decision:

| Server result | Example behavior |
| --- | --- |
| Enforce: allow | Resume the framework's normal tool dispatch. This also honors an administrator's configured allow on a grading failure. |
| Enforce: deny | Report the call `blocked`, then raise `ToolBlocked` before the tool body executes. |
| Enforce: escalate | Wait for the supplied human-approval callback, or report the call `blocked` and raise `ApprovalRequired` if no callback is configured. |
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
This requires findings and content access and permission to update the session as its
owner or with `sessions:write:any`.
For a service API key, configure `sessions:ingest`, `sessions:findings:read:any`,
`sessions:content:read:any` and `sessions:write:any` for transcript recording and for reporting human decisions, refusals and cancellations.
Lookup, permission, upload, content-scrub or readback failures block execution. The default reporting deadline is 10 seconds; configure
`human_audit_timeout` to change it. Recent human decisions accompany later grading
requests as context. Persist the human choice in your application if recovery is
needed; the example does not retry tools after a reporting failure.

## Submit results and inspect Watcher

After a turn, call `await monitor.record(native_history)` with the tool results
and final assistant answer. This uses the same hook with no pending input, so it
does not regrade old calls. If submission fails, retain the history and retry the
submission rather than executing the tools again.

The session's external ID is `other=openai-agents:<conversation_id>`. Query that ID in
Watcher to confirm the transcript and decisions. A successful hook response
confirms evaluation or request acceptance; transcript/decision storage runs after
the response and has no durability acknowledgement. Session-write permission is
required for recording even when the policy decision itself succeeds.

Watcher records each evaluated call as pending and settles it from the call's
result in a later request: a result without an `error` from a call Watcher let
through is recorded as completed. `error` means only that the tool failed while
running. A refused or cancelled call keeps the refusal text the agent saw as its
result, and its status goes into Watcher's decision record instead.

Refused and cancelled calls:

- The Monitor reports `blocked` for a Watcher denial or for an escalation with no
  approval callback. A person's rejection is already recorded as `blocked` with
  the human choice. A call cancelled while it is being decided, including while a
  person is asked, is reported as `cancelled`, without inventing an answer.
- `execute_tool` reports `cancelled` for a call cancelled while its tool runs.
- For a refusal or cancellation your application makes after Watcher let a call
  through, such as your own check refusing it or stopping its tool on the Runner
  path, call `await monitor.report_status(call_id, name, arguments, "blocked")`
  (or `"cancelled"`).

Reports use the same upload, readback, deadline (`human_audit_timeout`) and
permissions as human decisions, and update only a call whose Watcher evaluation
the Monitor received. A reported `blocked` or `cancelled` stands; a `completed`
or `unknown` status, which Watcher settles from the result text the agent saw,
is replaced. `report_status` returns `False` for a call with no Watcher
evaluation, and for a call already reported or being reported, including a
person's rejection, since the first report stands. When a report fails, the
refusal or cancellation still propagates, with the reporting failure as its
cause, and a later `record()` reports it (see below).

Calls whose tools failed:

- Build each tool with `function_tool(failure_error_function=failure_error_function(monitor))`,
  as `demo/enforce.py` does. A tool exception still reaches the model as Agents'
  default error text, and the Monitor sends that result with `error`. With Agents'
  default `failure_error_function`, a tool exception becomes plain output and the
  call is recorded as completed.
- `execute_tool` marks a tool exception itself before re-raising it.
- For an exception your own code catches, call `monitor.mark_failed(call_id, message)`
  before the next `before` or `record`.

A call the Monitor withholds without reporting its status at once is reported
after the next `record()`:

- `blocked` after a monitoring failure (a timeout, a transport error or a
  malformed response), or after an approval callback that raised or returned a
  non-boolean, or whose human-decision report failed. Only the execution status
  is reported, so it never invents a person's answer and keeps one already
  stored.
- `cancelled` when it was cancelled before Watcher answered it.
- The status of its report, when that report failed.

Watcher may hold no decision for such a call, or record one later, and stores
the call from the transcript `record()` sends. So `record()` then waits up to
`human_audit_timeout` for the call to be stored on any branch of the session,
pausing longer between lookups as it waits. It uploads the call's status,
creating its decision record if there is none, and reads it back. A decision
Watcher records afterwards keeps that status.

If a report fails, `record()` raises `StatusNotRecorded`, a `ToolBlocked`, after
the transcript was accepted. Its `failures` maps each call ID whose status the
Monitor could not confirm to its error; an upload stored before its readback
failed may already have recorded that status. A
failure a retry may fix (the call not stored in time, a transport failure, rate
limiting or a server error) is retried by later `record()` calls, up to
`late_report_attempts` (3 by default) in all; the exception's `retrying` names
those calls. After a permanent failure, such as a refused permission, or after
the last attempt, the Monitor stops reporting the call and lists it with its
error in `monitor.unrecorded`.

Cancelling `record()` stops these reports at once. A call whose report it stops
stays queued without using an attempt. Its status is unconfirmed, since an upload
may have been stored before the cancellation; a later report that finds it stored
does not upload it again. A report that failed before the cancellation counts as
usual, so check `unrecorded` after a cancellation too.

To retry a person's rejection whose report failed, call
`report_human_decision(..., approved=False)` again. The Monitor never released
the call, so this records the rejection even after Watcher has settled the call
from its refusal text, or after a status report stored `blocked`, unless a human
decision is already recorded. The call then leaves the queue and `unrecorded`.

A call still queued when the run ends, or listed in `unrecorded`, has no
confirmed status. When Watcher holds no `blocked` or `cancelled` status for such
a call, it settles the call from the next request carrying its result: completed
only if it let the call through (an allow, or a deferral in observe mode) and
the result has no `error`, otherwise `unknown`. A call Watcher answered with a
paused-mode bypass runs, so it is never queued, and `report_status` reports
nothing for it.

A tool input guardrail rejects a call before the lifecycle hook runs, so Watcher
never evaluates that call and its rejection message is recorded as a plain result.

You can also observe a conversation that already completed using
`await observe(client, conversation_id, native_history)` or `python -m demo.observe`.
That separate import path follows the organization's policy without an override,
assesses calls against their historical prefixes in batches of at most 32, and
submits the final transcript. Paused mode records history without grading.
Returned decisions are advisory to completed actions; they cannot prevent or
undo an effect, and the importer does not report an action as blocked.

A completed Responses history does not record which calls failed, so the
importer cannot tell. Pass `errors={call_id: {"type": "unknown", "message": "..."}}`
to `observe` for each call whose tool you know failed. Watcher records any result
you send unmarked, from a call it let through, as completed. The importer does
not report refusals or cancellations either, so a refused call it let through is
also recorded as completed.

When this retrospective observer runs against an organization in Enforce mode,
Watcher can store an assessment as an applied denial and count it in automatic
denial totals after the tool has run. Those records describe the assessment;
they do not show that execution was prevented.

## Scope and limitations

Use this example only with agents whose tools are all local `FunctionTool`s and
whose system instructions stay fixed. `ComputerTool` actions can run concurrently
with `on_tool_start`; the unsupported-tool error can arrive after the action has
executed, so this hook does not guard computer use. Provider-hosted tools,
handoffs and changing system instructions also need different adapters.
Native function-call IDs link the supported function results.

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
