# Mistral Vibe: native observation and optional pre-tool veto

Supported native file-tool conversation and final response.

**How it works.** `post_agent` supplies `messages.jsonl` and `session_id`.
Add the generated observe TOML to `.vibe/hooks.toml` in a trusted test project.
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
uv run --no-sync watcher-mistral-vibe-observe-settings > /tmp/watcher-mistral-vibe-observe.toml
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

Each SDK batch and final save have 10 seconds. The observe-only configuration
gives `post_agent` 15 seconds. The configuration with enforcement gives that same
completion hook 60 seconds; its pre-tool deadline is separate.

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
uv run --no-sync watcher-mistral-vibe-enforce-settings > /tmp/watcher-mistral-vibe-enforce.toml
```

**Enable the pre-tool check.** Merge `/tmp/watcher-mistral-vibe-enforce.toml` into the test hook config.
Keep your other permission hooks. It adds `watcher_mistral_vibe.pre_tool` and keeps
the completion observer. Set the same `WATCHER_URL` and `WATCHER_API_KEY`.

The command sets `WATCHER_EPHEMERAL_PRE_TOOL=1`. Without that explicit choice,
the bridge denies the call; it never selects this mode on its own.

The hook inherits the organization's Watcher policy without settings overrides.
In enforce mode, a matching allow permits native dispatch; deny and escalation
withhold the tool. This example does not provide a human approval interface.
Valid observe or paused responses leave native permissions in control. The hook
also honors an administrator's configured allow on grading failure. Malformed,
mismatched or unavailable decisions withhold execution.

`mode="full"` selects grading depth; it does not select auto mode or override
the organization's enforcement settings.

Full grading defaults to 420 seconds; `WATCHER_TIMEOUT_SECONDS`
can reduce that limit. The native pre-tool hook allows 480 seconds. The adapter
does not retry.

**Context.** `pre_tool` supplies a real call ID and validated arguments, but the
first `messages.jsonl` does not exist yet. The hook provides no other conversation.
This explicitly enabled mode always sends `messages=[]`. It checks the current
tool, not the developer's intent or prior actions. The returned call ID must match.
It is not a fallback for failed transcript loading.

**Recording.** `ephemeral=True` saves no early transcript, grade row or veto
decision; usage still counts. The completion observer saves the real final transcript
and makes separate retrospective judgments. Those do not recover the earlier decision.

The example sets native `strict=true`, so hook-process errors and timeouts also
block execution.

## Expected Watcher result

After a run, find `other=mistral-vibe:<session-id>` in Watcher. Check the available
context, tool results and final text. Local fixtures do not verify deployed
server storage or grading. The unrecorded pre-tool check does not save
its early decision.

## Limitations

The completion hook runs after tools finish. Native tests cover the documented
text and file-tool conversation only. Attachments and branch replay are outside
the tested scope. Deployed Watcher storage and real grading remain unverified.

Subagent dispatch is outside the tested scope. `PreToolInvocation` supplies
`parent_session_id` from the agent loop's session context. The bridge refuses
a nonempty value. Native child-agent dispatch remains unverified.

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

Tests cover conversion, call IDs, results and errors. Allowed native reads return
real fixture contents; denied or failed reads return none. While Watcher waits,
no native result reaches the model.

This checks result delivery. On its own, it does not prove that no tool has run.

Observation tests check the final transcript. These local tests do not verify
deployed Watcher storage, real grade quality or hosted provider behavior.

Pass scenario names for a subset, such as `bash tests/native/run.sh pending unit`.
Use `bash tests/native/run.sh observe` for observation alone. The pending check
requires that no native result reach the model before Watcher's reply.

The printed output directory holds logs, installed versions and JUnit results.
`metadata.yaml` describes each mode's current test scope and versions.

## References

- [vibe/core/hooks/models.py](https://github.com/mistralai/mistral-vibe/blob/d4b3223bbd74f83cbc08da4b9c3776c8ad196955/vibe/core/hooks/models.py)
- [vibe/core/session/session_logger.py](https://github.com/mistralai/mistral-vibe/blob/d4b3223bbd74f83cbc08da4b9c3776c8ad196955/vibe/core/session/session_logger.py)
- [vibe/core/types.py](https://github.com/mistralai/mistral-vibe/blob/d4b3223bbd74f83cbc08da4b9c3776c8ad196955/vibe/core/types.py)
