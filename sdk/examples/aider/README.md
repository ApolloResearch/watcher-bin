# Aider: observe completed file writes

Actual InputOutput.write_text invocations in sequential nonstreaming whole-file Coder runs.

**How it works.** Pass `ObservedModel` and `ObservedIO` to Aider's
`Coder.create()`. They capture full model requests and replies without streaming,
then record real calls to `InputOutput.write_text`.

Each write gets one UUID when it is invoked. These IDs belong to actual file I/O;
they are not tool IDs from the model. The adapter does not infer writes by parsing
assistant edit text.

After a tool runs, `send_capture` sends its `aider_write_file` record through
the public SDK in observe mode. Each grade sees the model input and reply that
led to that write. It does not see the write result or later model replies.

A final request with empty tool input saves Inspect messages, write outcomes and
the final answer. Repeated context from model turns stays repeated in the record.
Watcher decisions here cannot change native permissions or completed edits.

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

Set `PROMPT` and `MODEL_NAME`, plus `TARGET_FILE` for a file Aider may edit. From the disposable workspace, invoke the demo with the installed environment:

```sh
/absolute/path/to/example/.venv/bin/python /absolute/path/to/example/demo/observe.py
```

This intentional run needs native provider/service credentials; it is separate from isolated tests.

Call `run_aider(prompt, cwd, model, client, fnames=[...])` in a test workspace.
It creates a whole-file Coder without streaming and keeps Aider's normal permission
checks. Pass an `AsyncWatcherClient` with `WATCHER_URL` and a session-write key.
For several turns, inject the objects and keep the capture before uploading:

```python
from aider.coders import Coder
from watcher_aider.observation import Capture, ObservedIO, ObservedModel, run_prompt, send_capture

capture = Capture()
coder = Coder.create(
    main_model=ObservedModel("gpt-4o", capture),
    io=ObservedIO(capture, yes=False),
    fnames=["greeting.txt"],
    edit_format="whole",
    stream=False,
    use_git=False,
)
run_prompt(coder, capture, "Update the greeting.")
run_prompt(coder, capture, "Summarize the completed change without further edits.")
# Inside the application's async context, with its configured SDK client:
await send_capture(client, "application-session-id", capture)
```

Retry the same capture to retain operation IDs. Capture retention and retry policy
belong to the application. The older `send`/`run_hook` path still archives a supplied
message snapshot only; it cannot observe IO that has already happened elsewhere.

**Delivery.** Each write has a 10-second assessment budget.

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

The final save has a separate 10 seconds and is tried even if grading fails.
N writes can therefore use roughly 10 × (N + 1) seconds in SDK calls. Allow for
that total in any enclosing hook or process deadline.

Timeouts reach the caller. Server work may still finish and incur cost after the
client disconnects. An SDK error cannot undo an edit. To check live delivery,
find `aider:<application-session-id>` in Watcher and inspect context, write ID,
result and final text. That deployed path remains unverified.

## Synchronous monitoring

Set `WATCHER_SESSION_ID` to a unique application session identifier, in addition to the observation example’s `PROMPT`, `MODEL_NAME`, `TARGET_FILE` and credentials. From the disposable workspace, run:

```sh
uv run --project /absolute/path/to/example --no-sync python /absolute/path/to/example/demo/enforce.py
```

`--project` selects the installed environment while preserving the current disposable workspace.

Use `EnforcedIO(capture, session_id, client_factory, yes=False, pretty=False)`
from `watcher_aider.synchronous` instead of `ObservedIO`. Keep `ObservedModel`,
`run_prompt` and `send_capture` in the same sequential, nonstreaming whole-file Coder.

`InputOutput.write_text` waits for the applied Watcher decision. IDs are
UUIDs assigned to I/O calls, not model tool IDs. A denied write is recorded as
withheld before execution and leaves the file unchanged. An attempted write that
fails has a separate failure result. A write with no captured model context
is refused. Shell commands and writes outside the injected I/O are not covered.

The hook inherits the organization's Watcher policy without settings overrides.
In enforce mode, a matching allow permits native dispatch; deny and escalation
withhold the tool. This example does not provide a human approval interface.
Valid observe or paused responses leave native permissions in control. The hook
also honors an administrator's configured allow on grading failure. Malformed,
mismatched or unavailable decisions withhold execution.

`mode="full"` selects grading depth; it does not select auto mode or override
the organization's enforcement settings.

The monitored demo calls `send_capture(..., record_only=True)` to submit final
results without regrading earlier decisions. `WATCHER_TIMEOUT_SECONDS`
defaults to 420. A timeout does not stop server work or trigger a retry.

## Expected Watcher result

After a run, find `other=aider:<session-id>` in Watcher. Check the available
context, tool results and final text. Local fixtures do not verify deployed
server storage or grading.

## Limitations

Aider's upstream Python scripting API is not officially supported and may change
without backward compatibility. This example uses the public Watcher SDK unchanged.
Tests cover sequential whole-file Coder runs without streaming.

Other edit formats, streaming, concurrent Coders, attachments and compaction replay
are unverified. So are commands that write outside the injected I/O.

Dry runs produce no write observation. A write with no preceding captured model
reply is counted as unassociated; the adapter does not guess its context. Native
I/O errors keep their type and are raised again. They do not create a success record.

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

The printed output directory holds logs, installed versions and JUnit results.
`metadata.yaml` describes each mode's current test scope and versions.

## References

- [Python scripting and stability warning](https://github.com/Aider-AI/aider/blob/253f0368b873ba30d8ee26e463718f0c03614ddf/aider/website/docs/scripting.md)
- [Injected model and IO arguments](https://github.com/Aider-AI/aider/blob/253f0368b873ba30d8ee26e463718f0c03614ddf/aider/coders/base_coder.py#L125)
- [Native model completion](https://github.com/Aider-AI/aider/blob/253f0368b873ba30d8ee26e463718f0c03614ddf/aider/models.py#L970)
- [Whole-file edits call the injected IO](https://github.com/Aider-AI/aider/blob/253f0368b873ba30d8ee26e463718f0c03614ddf/aider/coders/wholefile_coder.py#L124)
- [Native write return/error and dry-run behavior](https://github.com/Aider-AI/aider/blob/253f0368b873ba30d8ee26e463718f0c03614ddf/aider/io.py#L478)
