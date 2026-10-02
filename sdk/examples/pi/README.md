# Pi: observation and synchronous monitoring

Monitor Pi's native tool calls and submit the current uncompacted branch to Watcher.
A Node extension waits for a Python bridge using the public Watcher SDK. The same
pre-tool extension follows server policy for observation or enforcement. This is
an experimental example, not an officially supported integration.

## Installation

Use Python 3.12, `uv` and Node 24.11.1. The manifests under `packages/` list
versions and dependencies for each component. Their lockfiles record the tested
environment. The Python component uses the adjacent Watcher SDK source directory.

The harness itself is a separate prerequisite: this example targets @earendil-works/pi-coding-agent 0.85.1.

From this directory:

```sh
uv sync --project packages/python
mkdir -p dist
npm pack ./packages/node --pack-destination dist --ignore-scripts
npm install --no-save --package-lock=false --ignore-scripts dist/watcher-pi-example-0.0.1.tgz
export PATH="$PWD/node_modules/.bin:$PATH"
export WATCHER_PYTHON="$PWD/packages/python/.venv/bin/python"
```

Install both components. The Node package does not install Python. Set
`WATCHER_PYTHON` to an absolute path to an interpreter with `watcher_pi_bridge`
and the Watcher SDK installed. The bridge calls installed modules or commands,
so it does not need sibling source files at runtime.

Set the variables in `demo/.env.example`; the demos do not load the file.
Set `WATCHER_URL`, a session-write `WATCHER_API_KEY`, and the provider settings
your native tool needs. Keep existing permission and monitoring hooks. Store
transcripts in a private directory and decide how long to keep them.

## Observation

Pass the installed extension to the invocation: `pi -e "$PWD/node_modules/watcher-pi-example/src/plugin.mjs"`. It captures message entries from `ctx.sessionManager.getBranch()` at `agent_end`. A branch containing compaction is refused. `demo/observe.mjs` re-exports the installed extension.

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

Each SDK batch and final save have 10 seconds. The Python observation process has
15 seconds in total. With the pre-tool plugin, agent_end submits only the final
transcript; it does not repeat historical grading or request an observe override.

Each completion waits for historical tool checks one at a time before the final
save. The outer deadline can stop the process before that save finishes. Newest
tool results or final text can then remain unrecorded, even if earlier prefixes
reached Watcher. Trying the final save after a grading error does not protect it
from the whole process being stopped.

The Node callback can finish even if Python times out or exits with an error.
Callback completion is not a Watcher recording acknowledgement; a timeout may
also end Python before it prints a recording-error message.

A longer outer deadline gives more time but does not guarantee a final save.
Treat a timeout as incomplete observation. Server work may still finish and be
billed; the adapter does not retry. The local tests do not verify deployed latency.

## Synchronous monitoring

Use `pi -e "$PWD/node_modules/watcher-pi-example/src/plugin.enforce.mjs"` instead of the observer. The awaited `tool_call` extension returns a native block on refusal and submits the completed transcript at agent_end. The callback supplies `ctx.cwd`. Later argument-mutating extensions, plugin loading failures and user-entered shell are outside verified scope.

This adapter inherits the Watcher organization's policy and sends no override.
In enforce mode, a matching allow permits ordinary native dispatch, including an
administrator-configured allow on a grading failure. Deny and escalation block;
the extension does not supply a human approval UI. In observe or paused mode,
a valid deferred result preserves Pi's ordinary execution and permission checks.

Mismatched identities, malformed outcomes, inconsistent provenance and SDK or
transport errors withhold the call. Full grading waits up to 420 seconds;
`WATCHER_TIMEOUT_SECONDS` can reduce that limit. The plugin subprocess deadline is
460 seconds. Client timeout does not stop server grading or its cost. No automatic
retry or terminal execution-status reporting is included.

## Expected Watcher result

Find the conversation in Analyzer using `pi:<native-session-id>` as its external ID.
Check the visible context and final assistant text. Check the tool IDs and
linked results too. A saved transcript alone does not prove that its tools were graded.

The hook response confirms evaluation or request acceptance, not durable storage.
Recording is asynchronous and needs session-write permission; query the session to
verify stored messages and decisions. Local fixture responses alone do not prove
real server persistence, grading quality or provider behavior.

## Limitations

- The converter handles native text, visible thinking, tool IDs and linked results directly. IDs must be unique and result names must match; attachments, compaction and branch replay are not covered.
- The observer runs after tools complete; the separately selected enforcement adapter can veto within its documented boundary.
- Model output and grader verdicts are local fixtures; hosted providers and deployed Watcher persistence remain unverified.
- Later argument-mutating extensions, plugin loading failures and user-entered shell commands are outside the verified boundary.

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
