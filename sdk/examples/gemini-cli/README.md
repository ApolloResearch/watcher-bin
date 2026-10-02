# Gemini CLI: native observation and optional pre-tool veto

Supported native text/tool conversation records and final text.

**What it does.** Add the generated observation settings to a test project's
`.gemini/settings.json`. `AfterAgent` supplies a JSONL transcript path and session
ID. The bridge converts the full transcript to Inspect messages with the public
SDK, grades completed tools, and saves results and final text.

It keeps parallel call IDs and delivered result order. The observer runs after
tools complete, so it cannot block them. It reads the completion transcript because
`AfterModel` strips non-text parts. Each upload contains the full snapshot; server
convergence handles repeated snapshots instead of a local append cursor.

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
uv run --no-sync watcher-gemini-cli-observe-settings > /tmp/watcher-gemini-cli-observe.json
```

When merging the generated object into native settings, set `hooksConfig.enabled` to `true`, as the contained native fixture does. Keep the existing authentication and permission settings.

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
`AfterAgent` 60 seconds for the whole completion.

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
uv run --no-sync watcher-gemini-cli-enforce-settings > /tmp/watcher-gemini-cli-enforce.json
```

**Enable the pre-tool check.** Merge `/tmp/watcher-gemini-cli-enforce.json` into the test hook config.
Keep your other permission hooks. It adds `watcher_gemini_cli.pre_tool` and keeps
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

**Context.** `BeforeTool` supplies prior user/context messages and exact tool
arguments, but no pending tool ID. `watcher_gemini_cli.pre_tool` reads that prior
transcript and sends one scalar ephemeral request. It does not invent or guess an ID.

The recorder may already contain an empty assistant text row before saving its
tool call. The adapter keeps that row. It does not mean the assistant turn is
complete or identify a pending tool. Missing or invalid prior context denies the call.

**Recording.** `ephemeral=True` saves no early transcript, grade row or veto
decision; usage still counts. The completion observer saves the real final transcript
and makes separate retrospective judgments. Those do not recover the earlier decision.

Gemini may continue when the hook produces no usable output. Caught Python or SDK
errors return a denial. If the process crashes or is killed, native handling still
applies.

## Expected Watcher result

After a run, find `other=gemini-cli:<session-id>` in Watcher. Check the available
context, tool results and final text. Local fixtures do not verify deployed
server storage or grading. The unrecorded pre-tool check does not save
its early decision.

## Limitations

Native tests cover `AfterAgent` and a real file read with local replies. They
do not verify deployed Watcher storage. Observation happens after tools run.
Attachments and branch replay are outside the tested scope.

Separate `functionResponse` records keep the order in which results arrive and
replace duplicate inline results. Older inline-only transcripts keep tool-array
order. Native transcripts can truncate tool output.

The converter rejects the older top-level `messages` shape. The tested writer
uses separate ID records or `$set.messages` updates.

Subagent dispatch is outside the tested scope. The bridge refuses a nonempty
`parent_session_id` if one is supplied. The native tests do not establish that this field reliably identifies child
agents. Its absence does not prove that this is a root session.

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

- [packages/core/src/hooks/types.ts](https://github.com/google-gemini/gemini-cli/blob/9c1b0a610534d6f8120964cf2672c07807d8fc90/packages/core/src/hooks/types.ts)
- [packages/core/src/services/chatRecordingTypes.ts](https://github.com/google-gemini/gemini-cli/blob/9c1b0a610534d6f8120964cf2672c07807d8fc90/packages/core/src/services/chatRecordingTypes.ts)
- [packages/core/src/services/chatRecordingService.ts](https://github.com/google-gemini/gemini-cli/blob/9c1b0a610534d6f8120964cf2672c07807d8fc90/packages/core/src/services/chatRecordingService.ts)
- [packages/core/src/hooks/hookTranslator.ts](https://github.com/google-gemini/gemini-cli/blob/9c1b0a610534d6f8120964cf2672c07807d8fc90/packages/core/src/hooks/hookTranslator.ts)
