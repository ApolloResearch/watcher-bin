# Kilo Code: observation and synchronous monitoring

Supported linear text/tool parts from native session snapshots. This collection is experimental and is not an officially supported integration. Python calls only the public Watcher SDK; native components preserve their normal authorization and validation behavior.

## Installation

Use Python 3.12, `uv` and Node 24.11.1. The manifests under `packages/` list
versions and dependencies for each component. Their lockfiles record the tested
environment. The Python component uses the adjacent Watcher SDK source directory.

The harness itself is a separate prerequisite: this example targets @kilocode/cli 7.6.2.

From this directory:

```sh
uv sync --project packages/python
mkdir -p dist
npm pack ./packages/node --pack-destination dist --ignore-scripts
npm install --no-save --package-lock=false --ignore-scripts dist/watcher-kilocode-example-0.0.1.tgz
export PATH="$PWD/node_modules/.bin:$PATH"
export WATCHER_PYTHON="$PWD/packages/python/.venv/bin/python"
```

Install both components. The Node package does not install Python. Set
`WATCHER_PYTHON` to an absolute path to an interpreter with `watcher_kilocode_bridge`
and the Watcher SDK installed. The bridge calls installed modules or commands,
so it does not need sibling source files at runtime.

Set the variables in `demo/.env.example`; the demos do not load the file.
Set `WATCHER_URL`, a session-write `WATCHER_API_KEY`, and the provider settings
your native tool needs. Keep existing permission and monitoring hooks. Store
transcripts in a private directory and decide how long to keep them.

## Observation

Select the installed `plugin.mjs` in the project plugin configuration. It waits for `session.idle`, then reads `client.session.messages()`. Use the absolute installed path `node_modules/watcher-kilocode-example/src/plugin.mjs`; `demo/observe.mjs` re-exports the same installed plugin.

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
15 seconds in total, with either the observe-only or enforcement plugin.

Each completion waits for historical tool checks one at a time before the final
save. The outer deadline can stop the process before that save finishes. Newest
tool results or final text can then remain unrecorded, even if earlier prefixes
reached Watcher. Trying the final save after a grading error does not protect it
from the whole process being stopped.

The Node callback can finish even if Python times out or exits with an error.
Callback completion alone does not establish durable Watcher storage; a timeout
may end Python before it can report an upload failure.

A longer outer deadline gives more time but does not guarantee a final save.
Treat a timeout as incomplete observation. Server work may still finish and be
billed; the adapter does not retry. The local tests do not verify deployed latency.

## Synchronous monitoring

Replace the observation plugin entry with the installed `plugin.enforce.mjs` (or `demo/enforce.mjs`). `tool.execute.before` awaits approval and the same plugin retains idle observation. Install after plugins that rewrite arguments. Later mutations, plugin loading failures and unrelated background I/O are outside verified scope.

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
420 seconds; `WATCHER_TIMEOUT_SECONDS` can reduce that limit. The plugin
subprocess deadline is 460 seconds. A client timeout does not stop work or cost
on the server.

## Expected Watcher result

Find the conversation in Analyzer using `kilocode:<native-session-id>` as its external ID.
Check the visible context and final assistant text. Check the tool IDs and
linked results too. A saved transcript alone does not prove that its tools were graded.

Local fixtures exercise native ordering and public SDK serialization. Their fixture replies do not establish deployed Watcher persistence, real grading quality or provider behavior.

## Limitations

- Native dispatch verified for the captured file-tool conversation; deployed Watcher persistence and real grading remain unverified.
- Only supported text/tool content; attachments and branch replay are not covered
- Tool results are projected in stored part order; no live completion ordering is claimed
- The observer runs after tools complete; the separately selected enforcement adapter can veto within its documented boundary.
- The 15-second plugin bridge deadline can truncate multi-batch observations on slow servers
- Later argument-mutating plugins and plugin loading failures are outside the verified boundary.

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
