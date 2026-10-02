# OpenHands: native lifecycle integration

Native Conversation callback messages and completed tool results.

**How it works.** Install `openhands-sdk==1.46.0`. `Recorder` is a native
Conversation callback. It reads public events through
`LLMConvertibleEvent.to_llm_message().to_chat_dict()`.

Call `run_openhands(prompt, cwd, model, client)` for a minimal run with no tools.
Or register `Recorder` on your configured Agent and send its messages after the
run. The public SDK gets Inspect messages and the native external ID, grades
completed tools and saves the final history.

This observer cannot block tools. Capture and delivery are separate, so an SDK
error cannot change a tool's output.

## Installation and configuration

Use Python 3.12+ and `uv`. From this directory:

```sh
uv sync --no-editable
```

The development environment uses the adjacent Watcher SDK source directory.
`pyproject.toml` lists the package version, dependencies and commands. `uv.lock`
records the tested environment. Once installed, the adapter uses installed
packages; it does not need the source checkout at runtime.

Set `WATCHER_URL` and a session-write `WATCHER_API_KEY` for intentional delivery.
`demo/.env.example` lists safe values; it is not loaded automatically. Keep normal
native permissions and existing monitoring configuration.

## Observation

Set `PROMPT`, `MODEL_NAME` and `LLM_API_KEY` for the selected provider. From the disposable workspace, invoke the demo with the installed environment:

```sh
/absolute/path/to/example/.venv/bin/python /absolute/path/to/example/demo/observe.py
```

This intentional run needs native provider/service credentials; it is separate from isolated tests.

Set `WATCHER_URL` and a session-write `WATCHER_API_KEY`. The library accepts
an `AsyncWatcherClient`; use it as an async context manager. Start in a test
workspace and keep your normal permissions and monitoring in place. After the
run, find `other=openhands:<native-session-id>` in Watcher and check the final text
and available tool results. Delivery to a deployed Watcher server is unverified.

Retrospective assessment follows the organization's Watcher policy without a
settings override, including when the mode is locked. Active observe or enforce
settings run rules and triage with `mode="triage_only"`; the full grading stage
does not run. Paused mode records the transcript without grading. Decisions are
advisory to actions that already finished: a returned deny cannot undo a tool,
and the adapter does not report that the action was blocked. Use the pre-tool
monitor where available to withhold execution.

In Enforce mode, Watcher can store a retrospective assessment as an applied
denial and count it in automatic-denial totals after the tool has run. Those
records describe the assessment; they do not show that execution was prevented.

Each tool is graded using only the transcript up to its call. Calls with the
same preceding messages are batched, at most 32 per request. The adapter requires
matching IDs and consistent policy outcomes. It then tries to save the final results and
text, even if a grade failed.

Each batch and final save have a 10-second budget. Several batches can take longer,
so the native hook deadline must cover the whole delivery. Timeouts count as
incomplete observation. Server work may still finish and be billed; the adapter
does not retry. The local tests do not verify deployed server latency.

## Synchronous monitoring

Import `run_monitored(agent, prompt, cwd)` from `demo/enforce.py` and pass your configured native Agent and tools. The function binds the callback before executing the synchronous conversation and flushes observation afterward.

Use `EnforcementRecorder` from `watcher_openhands.synchronous` in place of
`Recorder`. Pass it as a `LocalConversation` callback and call
`recorder.bind(conversation)` before sending a message. Run synchronous
`conversation.run()`; from async code, use a worker thread. Supply a factory
that creates a fresh `AsyncWatcherClient`.

The synchronous `ActionEvent` callback holds dispatch while Watcher grades. It
adds a block on refusal or error. A decision that permits dispatch leaves blocked state
unchanged, including refusals added during the wait. Native confirmation settings
still apply. An unbound recorder is an error; `conversation.arun()` is not covered.

The hook inherits the organization's Watcher policy without settings overrides.
In enforce mode, a matching allow permits native dispatch; deny and escalation
withhold the tool. This example does not provide a human approval interface.
Valid observe or paused responses leave native permissions in control. The hook
also honors an administrator's configured allow on grading failure. Malformed,
mismatched or unavailable decisions withhold execution.

`mode="full"` selects grading depth; it does not select auto mode or override
the organization's enforcement settings.

Submit final results with
`send(client, str(conversation.id), convert(recorder.messages), record_only=True)`
to preserve earlier applied decisions. `WATCHER_TIMEOUT_SECONDS` defaults to 420 seconds; timeouts
do not stop server work or trigger a retry.

## Expected Watcher result

After a run, find `other=openhands:<session-id>` in Watcher. Check the available
context, tool results and final text. Local fixtures do not verify deployed
server storage or grading.

## Limitations

Local tests run native callbacks and tools with fixture replies. They do not
verify delivery to a deployed server. The converter keeps parallel IDs and
available results. It rejects unknown content. Subagents, compaction and branch
replay remain unverified. Your application owns retries and retention after a failure.

## Tests

Run the complete test suite from this directory:

```sh
bash tests/native/run.sh
```

The runner builds the SDK and adapter packages, installs them in a fresh
environment, and tests them outside the source checkout. Package downloads finish
before the tests start. `WATCHER_SDK_WHEEL` can select a prebuilt SDK wheel.
`WATCHER_EXAMPLE_RUN_DIR` selects a parent for a fresh output directory.

Docker and `uv` are required. Each runtime container has no network access,
a fresh home and workspace, a read-only root, dropped capabilities and
`no-new-privileges`. Model and Watcher fixtures run inside it. No host credentials,
home, hooks or Docker socket are mounted.

Native tests inspect the file itself while Watcher waits and after it replies.
Cases cover allow, deny, escalation, deferred mode, wrong IDs, missing outcomes
and HTTP errors. They also check call IDs and the final observation.

Separate SDK tests check the reply contract. Those checks alone do not prove that
the native tool waits before it runs.

These local tests do not verify deployed Watcher storage, real grade quality or
hosted provider behavior.

Another native test adds a local refusal while Watcher is pending. It checks that
a later Watcher allow cannot clear that refusal or release the file write.

The printed output directory holds logs, installed versions and JUnit results.
`metadata.yaml` describes each mode's current test scope and versions.

## References

- [examples/01_standalone_sdk/11_async.py](https://github.com/OpenHands/software-agent-sdk/blob/e2889cd49d3ef7fe06d52c8a2355b8a769b97d88/examples/01_standalone_sdk/11_async.py)
- [openhands-sdk/openhands/sdk/llm/message.py](https://github.com/OpenHands/software-agent-sdk/blob/e2889cd49d3ef7fe06d52c8a2355b8a769b97d88/openhands-sdk/openhands/sdk/llm/message.py)
- [openhands-sdk/openhands/sdk/event/llm_convertible/message.py](https://github.com/OpenHands/software-agent-sdk/blob/e2889cd49d3ef7fe06d52c8a2355b8a769b97d88/openhands-sdk/openhands/sdk/event/llm_convertible/message.py)
