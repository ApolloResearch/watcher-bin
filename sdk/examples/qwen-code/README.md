# Qwen Code: native Stop integration

Supported native text/tool history with exact model call IDs.

**How it works.** Add the generated observe settings to a test project's
`.qwen/settings.json`. Stop supplies the JSONL transcript path and `session_id`.
The bridge converts the full snapshot to Inspect messages and submits completed
tool inputs to `pre_tool_use_hook` in observe mode.

A final request uses empty tool input. It submits the
text, call IDs, tool results and final answer. These checks do not block tools.
Each upload is a full snapshot; repeated uploads rely on the server's handling
of repeated history, not a local append cursor.

## Installation and configuration

Use Python 3.12+, `uv`, and an existing native harness installation with its normal credentials. From this directory:

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

Generate observation settings for the installed Python environment:

```sh
uv run --no-sync watcher-qwen-code-observe-settings > /tmp/watcher-qwen-code-observe.json
```

The command prints settings; it does not install hooks or change their deadlines.
Use the steps below to load the file. Keep the Python environment at its current
path. The command fills `__WATCHER_PYTHON__` in the templates under `demo/`;
do not install a template with that marker still in it.

Start in a test project and keep your current permissions and monitoring hooks.
Use the settings command above to bind the Python environment. It does not install
anything. Observation errors print a warning and return neutral hook output.
Failed delivery is not retried. Each SDK call may delay completion by up to
10 seconds.

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

Each SDK batch and final save have 10 seconds. Both generated configurations give
the `Stop` hook 15 seconds for the whole completion.

Each completion waits for historical tool checks one at a time before the final
save. The outer deadline can stop the process before that save finishes. Newest
tool results or final text can then remain unrecorded, even if earlier prefixes
reached Watcher. Trying the final save after a grading error does not protect it
from the whole process being stopped.

A longer outer deadline gives more time but does not guarantee a final save.
Treat a timeout as incomplete observation. Server work may still finish and be
billed; the adapter does not retry. The local tests do not verify deployed latency.

## Synchronous monitoring

Generate the pre-tool configuration. The hook follows the Watcher organization's
observe, enforce or paused setting.

```sh
uv run --no-sync watcher-qwen-code-enforce-settings > /tmp/watcher-qwen-code-enforce.json
```

Use `/tmp/watcher-qwen-code-enforce.json` in the same test settings directory
as the observer. It adds `PreToolUse` and keeps `Stop`.

The hook inherits the organization's Watcher policy without settings overrides.
In enforce mode, a matching allow permits native dispatch; deny and escalation
withhold the tool. This example does not provide a human approval interface.
Valid observe or paused responses leave native permissions in control. The hook
also honors an administrator's configured allow on grading failure. Malformed,
mismatched or unavailable decisions withhold execution.

`mode="full"` selects grading depth; it does not select auto mode or override
the organization's enforcement settings.

Monitored completion sends the final transcript without regrading earlier calls.

The SDK deadline defaults to 420 seconds and can be reduced with `WATCHER_TIMEOUT_SECONDS`. Native command/plugin deadlines allow additional time around that request. A timeout does not cancel server-side grading or its cost, and the example never retries automatically.

## Expected Watcher result

After a run, find `other=qwen-code:<session-id>` in Watcher. Check the available
context, tool results and final text. Local fixtures do not verify deployed
server storage or grading.

## Limitations

The observer grades tools after they run and cannot block them. The separate
pre-tool hook supplies synchronous monitoring. Native tests cover the documented
text and file-tool conversation. Attachments and branch replay are outside scope.

Function results need call IDs. The converter rejects a missing ID rather than
matching by tool name. Native tests use local replies; deployed Watcher storage
and real grading remain unverified.

**Call identity.** Qwen uses `tool_use_id` for a hook invocation and
`tool_call_id` for the model's tool call. The adapter requires `tool_call_id` to
link parallel calls with recorded results. It refuses a missing ID.

Caught SDK errors return a native denial. Qwen owns the behavior when a hook
cannot start, crashes or times out. The adapter leaves normal permissions in
place. It supports linear visible history and rejects compaction or unsupported
content.

Subagent dispatch is outside this example’s verified scope. The pinned hook contract uses `agent_id` to identify a subagent; the bridge refuses that field before reading history or grading. It also rejects a supplied `parent_session_id`. The contract-level refusal is tested, but no native child-agent run is claimed.

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

The tests combine native call IDs and results with independent file-open events.
In the pending case, the fixture records zero file opens before releasing
Watcher's reply. These event checks do not rely only on what the model receives.

The tests also cover allow, deny and error paths, and the final transcript.
These local checks do not verify deployed Watcher storage, real grade quality or
hosted provider behavior.

Pass scenario names for a subset, such as `bash tests/native/run.sh allow deny pending timeout`.
Use `bash tests/native/run.sh observe` to run observation alone. The pending case
must capture evidence before the Watcher reply is released.

The printed output directory holds logs, installed versions and JUnit results.
`metadata.yaml` describes each mode's current test scope and versions.

## References

- [packages/core/src/hooks/types.ts](https://github.com/QwenLM/qwen-code/blob/fdcd7c2761e4ae18d578cf1413ae8d43f58b3e2c/packages/core/src/hooks/types.ts)
- [packages/core/src/services/chatRecordingService.ts](https://github.com/QwenLM/qwen-code/blob/fdcd7c2761e4ae18d578cf1413ae8d43f58b3e2c/packages/core/src/services/chatRecordingService.ts)
- [packages/core/src/utils/transcript-records.ts](https://github.com/QwenLM/qwen-code/blob/fdcd7c2761e4ae18d578cf1413ae8d43f58b3e2c/packages/core/src/utils/transcript-records.ts)
