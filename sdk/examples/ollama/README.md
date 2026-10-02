# Ollama → Watcher

Use this example to monitor application-owned tool calls and submit their native
conversation through the public Watcher SDK. One pre-tool integration follows
Watcher's configured enforcement mode. This is an experimental example, not an
officially supported integration.

## Install and configure

Use Python 3.12 or later and `uv`. From this directory:

```sh
uv sync --python 3.12
```

The development environment uses adjacent SDK source. For installation with a
released SDK wheel, follow the [shared setup guide](../README.md). `uv build --wheel`
builds this example as a separate package.

Set the variables listed in `demo/.env.example`: the provider base URL/model and
Watcher URL/key. Google also requires a provider API key. The demos read shell
environment variables directly; they do not load `.env` files. A Watcher key needs
session-write permission to record conversations. `WATCHER_TIMEOUT` sets the
grading deadline in seconds, default 420.

## Monitor application tools

Create one `Monitor` per conversation and keep its ID and full returned history
across turns. Register asynchronous tool callbacks in the `functions` argument
to `run_turn`, imported from `watcher_ollama.monitoring`. The runnable registration,
provider tool declarations and model loop are in `demo/enforce.py`:

```sh
.venv/bin/python demo/enforce.py
```

`run_turn` asks the native provider for a buffered response, converts pending calls,
and waits for Watcher before dispatching the registered callbacks. Every call in
a pending batch is checked before any callback starts. Other clients, provider-hosted
tools and application side effects outside this dispatcher are not intercepted.

| Watcher result | Example behavior |
| --- | --- |
| Enforce: allow | Run the registered callbacks, including when an administrator explicitly configures grading failures to allow. |
| Enforce: deny | Raise `Withheld` before any callback in the pending batch starts. |
| Enforce: escalate | Await the supplied application approval callback, or raise `ApprovalRequired` without one. |
| Observe or paused: deferred | Preserve ordinary application execution and permission checks. |

Transport errors, malformed results and mismatched identities block execution.
The default inherits server policy. `Monitor(..., enforcement="observe")`,
`"enforce"` or `"paused"` requests an explicit override, which an administrator
lock can reject. The hook's `mode="full"` selects grading depth, not an automatic
approval workflow.

For a human in the loop, pass an asynchronous `approval_callback` receiving
`tool_use_id`, `tool_name`, `tool_input` and `outcome`. Connect it to an authorized
person's approval UI or queue. Only literal `True` releases the call; false values,
errors and absent callbacks withhold it. Callback arguments are copied so the
approval UI cannot modify pending execution. This helper does not include an
approval UI, durable interruption, automatic review model or persisted human-choice
audit. An unattended caller omits the callback and stops on escalation.

## Native history and submission

Use native `ollama.Message` histories. Ollama supplies no call IDs in the pinned version, so stable local IDs come from full-history positions. Results link by tool name. Parallel outstanding calls with the same name are ambiguous and rejected; a name can be reused after its earlier result. Text and buffered function calls are supported. Use an existing Ollama server; the example does not start a server or download a model.

Keep turns sequential and retain the complete history. Results and final assistant
text are submitted through the same hook without regrading completed calls. The
external session ID is `other=<session_id>`. A successful hook response confirms
acceptance, not durable storage: recording runs asynchronously. Query the session
in Watcher to confirm stored messages and decisions.

A Monitor never repeats an attempted tool ID. This state is in memory and does
not guarantee exactly-once execution across restarts. Grading may finish after
the caller's timeout. Completed side effects are not rolled back.

If result submission fails, `run_turn` raises `RecordingFailed` with the native
`history` and converted `messages`. Retain them, retry only
`await monitor.record(error.messages)`, and use `error.history` for the next turn.
Do not rerun a tool to retry submission. Applications must persist recovery state
if it must survive cancellation or a crash.

## Observe without owning tool execution

`watcher_ollama.integration.complete` and `demo/observe.py` offer a separate
asynchronous observer. Provider responses return before grading finishes; call
`flush()` after producers stop, then inspect `error_count`, `errors` and `judgments`.
This path inherits organization policy without an override. Paused mode submits
history without grading. Returned decisions are advisory to completed actions
and cannot stop or undo a tool effect.

In Enforce mode, Watcher can store a retrospective assessment as an applied
denial and count it in automatic-denial totals after the tool has run. Those
records describe the assessment; they do not show that execution was prevented.

Its queue retains at most 32 pending snapshots and the latest 128 outcomes/errors.
A full queue reports an error and drops the newest snapshot. It submits snapshots
in order, does not retry grades, and does not survive process exit. Unsupported
or incomplete responses produce visible errors. Complete matching grades enter
`judgments`; transcript acceptance alone does not establish grading.

## Development and verification

`src/` contains conversion and dispatch; `demo/` contains runnable provider clients;
`tests/` uses the installed provider client with local model and Watcher HTTP fixtures.
It checks real callback effects, pending decisions, refusal, observation, identity
matching and history recovery. These fixtures alone do not establish a real Watcher
server's persistence or hosted provider behavior. `metadata.yaml` records verification
versions and scope.

Install dependencies before running with outbound networking disabled:

```sh
env -i PATH="$PATH" ../run-without-network.sh env \
  PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONDONTWRITEBYTECODE=1 \
  "$PWD/.venv/bin/python" -m pytest -p pytest_asyncio.plugin \
  --noconftest -c pyproject.toml tests -q
```

The Linux wrapper requires permission to create a fresh network namespace and
stops if isolation fails. See the [metadata guide](../METADATA.md) for verification fields.
