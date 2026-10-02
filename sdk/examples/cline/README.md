# Cline: observation and synchronous monitoring

Public canonical history of a local root session at TaskComplete. This collection is experimental and is not an officially supported integration. Python calls only the public Watcher SDK; native components preserve their normal authorization and validation behavior.

## Installation

Use Python 3.12, `uv` and Node 24.11.1. The manifests under `packages/` list
versions and dependencies for each component. Their lockfiles record the tested
environment. The Python component uses the adjacent Watcher SDK source directory.

The harness itself is a separate prerequisite: this example targets Cline CLI 3.0.61 and installs its history reader dependency @cline/core 0.0.82.

From this directory:

```sh
uv sync --project packages/python
mkdir -p dist
npm pack ./packages/node --pack-destination dist --ignore-scripts
npm install --no-save --package-lock=false --ignore-scripts dist/watcher-cline-history-example-0.1.0.tgz
export PATH="$PWD/node_modules/.bin:$PATH"
export WATCHER_PYTHON="$PWD/packages/python/.venv/bin/python"
```

Install both components. The Node package does not install Python. Set
`WATCHER_PYTHON` to an absolute path to an interpreter with `watcher_cline_bridge`
and the Watcher SDK installed. The bridge calls installed modules or commands,
so it does not need sibling source files at runtime.

Set the variables in `demo/.env.example`; the demos do not load the file.
Set `WATCHER_URL`, a session-write `WATCHER_API_KEY`, and the provider settings
your native tool needs. Keep existing permission and monitoring hooks. Store
transcripts in a private directory and decide how long to keep them.

## Observation

Copy the packaged `TaskComplete` hook into the project’s `.cline/hooks/` directory and make it executable. Locate the packaged hook with `importlib.resources.files("watcher_cline_bridge") / "hooks" / "TaskComplete"` using the installed Python interpreter. The hook invokes the installed module and requires `WATCHER_PYTHON`. Set `WATCHER_HISTORY_READER` to the absolute installed `node_modules/.bin/watcher-cline-history` executable when the hook environment does not inherit your configured PATH. `demo/observe.sh` is the same module invocation. The bridge reads `ClineCore.readMessages(rootSessionId)`, including the initial user prompt. Only local root sessions are supported; subagent callbacks are refused.

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

Add the packaged `PreToolUse` hook and copy `TaskCompleteMonitored` as
`.cline/hooks/TaskComplete`, replacing the observation-only completion hook. Make
both files executable. This completion hook uploads final results without
regrading tools already checked before execution. `demo/enforce.sh` shows its installed module invocation. It reads current public history and returns Cline’s native cancel control on refusal. The native deadline is 120 seconds: the history reader gets 25 seconds, grading defaults to and is capped at 60 seconds, leaving 35 seconds for startup and response. `WATCHER_TIMEOUT_SECONDS` can reduce grading time. A delivered cancellation aborts the task, so a denied run has no final answer or completed result. Cline logs and ignores hook startup errors, crashes, invalid output and native timeouts; those cases can release a tool. This is not unconditional prevention.

The hook inherits the organization's Watcher policy without settings overrides.
In enforce mode, a matching allow permits native dispatch; deny and escalation
withhold the tool. This example does not provide a human approval interface.
Valid observe or paused responses leave native permissions in control. The hook
also honors an administrator's configured allow on grading failure. Malformed,
mismatched or unavailable decisions withhold execution.

`mode="full"` selects grading depth; it does not select auto mode or override
the organization's enforcement settings.

Monitored completion submits the final transcript without regrading earlier calls.
Full grading waits up to
60 seconds; `WATCHER_TIMEOUT_SECONDS` can reduce that limit. A client timeout does not stop work or cost
on the server.

## Expected Watcher result

Find the conversation in Analyzer using `cline:<native-session-id>` as its external ID.
Check the visible context and final assistant text. Check the tool IDs and
linked results too. A saved transcript alone does not prove that its tools were graded. A denied task has no final answer.

Local fixtures exercise native ordering and public SDK serialization. Their fixture replies do not establish deployed Watcher persistence, real grading quality or provider behavior.

## Limitations

- Stored canonical history excludes some generated system context; only linear local root sessions verified
- Subagent callbacks are rejected; remote/hub history and compaction require separate verification
- The observer runs after tools complete; deployed Watcher grading and persistence remain unverified.
- Native startup/crash/invalid-output/timeout failures are logged and ignored by Cline; a delivered cancel aborts the task without final answer.
- The public history reader has a 25-second timeout; grading is capped at 60 seconds within the native 120-second hook deadline.

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

Tests cover conversion, call IDs, tool results and errors on the native path
described above. Pre-tool cases check that tools wait for an allow and stay blocked
on deny or error. The observe tests check the final transcript.

These local tests do not verify deployed Watcher storage, real grade quality or
hosted provider behavior.

Run the full suite to include both Python and Node checks. A selected enforcement
scenario leaves those component suites out.

File-access counts do not show which process made each read, or its exact time.
Call IDs and tool results add evidence. The tests do not cover unrelated background
I/O.

The printed output directory holds logs, installed versions and JUnit results.
`metadata.yaml` describes each mode's current test scope and versions.
