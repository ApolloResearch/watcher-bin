# Haystack with Watcher

This example connects Haystack's native agent runner to Watcher through the public
Python SDK. The same integration point follows the server's enforce, observe or
paused setting. It also provides a completed-history observer for applications
that only need retrospective monitoring.

## Install

Use Python 3.12. From this directory:

```bash
uv sync --frozen --python 3.12
export WATCHER_URL="https://your-watcher-server/api"
export WATCHER_API_KEY="your-watcher-key"
```

The example pins its native framework dependencies in `pyproject.toml` and
`uv.lock`. To install it in an existing application, use `python -m pip install .`.
Use a Watcher key with `sessions:ingest` to store transcripts. Reading sessions or
reporting human choices additionally requires the permissions described below.

## Connect an application

Create a public `AsyncWatcherClient` with your Watcher URL and key, then use
`MonitoredGenerator` with your application's configured model and tools:

```python
from haystack.components.agents import Agent
from haystack.dataclasses import ChatMessage
from watcher_haystack import Monitor, MonitoredGenerator

monitor = Monitor(watcher_client, conversation_id)
agent = Agent(
    chat_generator=MonitoredGenerator(your_chat_generator, monitor),
    tools=your_tools,
)
agent.warm_up()
result = await agent.run_async(messages=[ChatMessage.from_user(user_message)])
await monitor.record(result["messages"])
```

Keep one monitor and a stable conversation ID per conversation. The native
`Agent.run_async` runner owns tool dispatch and collects actual results. All calls in
one model response are checked before that response can reach tool execution.
A refused call withholds its whole response; earlier completed turns are not
rolled back. The application must submit the native final history after a
successful turn. Do not retry tool execution to repair a failed transcript upload.

## Policy and human approval

| Watcher result | Native behavior |
| --- | --- |
| Applied allow | Resume the native tool loop. |
| Applied deny | Stop before the pending response's tools run. |
| Escalate without an approval callback | Stop unattended execution. |
| Escalate with an approval callback | Await the human choice, record it, then allow or refuse. |
| Deferred in observe or paused mode | Preserve the framework's ordinary execution and permissions. |
| Network error or invalid/mismatched result | Stop before execution. |

`Monitor(..., enforcement="server")` is the default. An explicit `"observe"`,
`"enforce"` or `"paused"` selection requests a server settings override and may
be rejected by an administrator lock. An administrator's configured response to
a grading failure is an applied policy decision; a transport failure is not.

For a human-in-the-loop application, pass an async `approval_callback` accepting
`tool_use_id`, `tool_name`, `tool_input` and `outcome` as keyword arguments. It must
obtain an authorized human choice and return literal `True` or `False`. The monitor
uploads that choice with the public SDK and confirms the stored human choice
and tool status before releasing an approval, preserving the original evaluation
and grades. This requires findings and content access and permission to update the
session as its owner or with `sessions:write:any`.
For a service API key, configure `sessions:ingest`, `sessions:findings:read:any`,
`sessions:content:read:any` and `sessions:write:any` for transcript recording and human-decision reporting.
A reporting error blocks execution. The example includes no approval UI or persistent approval queue.

## Completed-history observation

The completed-history observer inherits the server's configured mode, including
paused. Its decisions are advisory for actions that have already happened; it
cannot block or reverse them and does not upload fabricated execution outcomes.
Paused bypasses and grading-failure fallbacks are valid responses, but are not
reported as completed judgments. No settings-read permission or observe-mode
override is required.

In Enforce mode, Watcher can store a retrospective assessment as an applied
denial and count it in automatic-denial totals after the tool has run. Those
records describe the assessment; they do not show that execution was prevented.

## Run the demonstrations

```bash
# Native agent execution under your Watcher policy
uv run --frozen --python 3.12 python -m demo.enforce

# Completed-history observation, after the native tools have run
uv run --frozen --python 3.12 python -m demo.observe
```

Both demonstrations use the installed framework with a deterministic local model
and arithmetic tools, so they need no model-provider account. Their Watcher calls
use the URL and key above. The synchronous demonstration emits the native final
transcript; the observer emits completed judgments. Look up the external ID
`other=haystack:<conversation_id>` in Watcher to inspect the stored history.

Hook success acknowledges the request, not durable transcript storage. Use the
SDK's session and trajectory queries when persistence confirmation is required.

## Tests and scope

```bash
../run-without-network.sh env HAYSTACK_TELEMETRY_ENABLED=false OTEL_SDK_DISABLED=true \
  .venv/bin/python -m pytest tests
```

The Linux isolation helper needs `sudo` and prevents external network access.
The tests run the installed native agent with local model and SDK transport
fixtures. They check actual tool effects, pending decisions, denials, unattended
escalation, configured observation, human approval/refusal and transcript identity.
These fixture tests do not establish hosted-provider or deployed Watcher behavior.
`metadata.yaml` records the separately verified versions and environments.

The wrapped chat generator must accept `messages` and `tools` and return one complete native reply. Haystack wraps monitor refusals in `PipelineRuntimeError`; its cause carries the refusal. Streaming callbacks are outside this example.

Only finalized text and function tools are supported. Provider-hosted tools run
before this integration can inspect their responses and cannot be prevented here.
The completed-history observer cannot prevent any tool side effect. Neither path
provides durable retries or exactly-once tool execution across process restarts.

`src/` contains the reusable adapters, `demo/` the runnable clients, and `tests/`
the executable checks. Build a wheel with `uv build --wheel` when distributing
your own application package.
