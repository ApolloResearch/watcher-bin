# Continue CLI: public session export

Explicit public version-one terminal export after the run; no automatic hook delivery.

**How it works.** Continue's terminal `/export` command writes versioned JSON
with the session ID and stored history. Pass that file on stdin to
`watcher_continue.integration`. It reads the public export, not private session files.

The adapter keeps the initial prompt, call IDs, completed tool outputs and final
text. It sends retrospective tool grades and the final transcript through the
public Watcher SDK.

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

After the native terminal `/export` action, use the actual exported filename:

```sh
export_file="/absolute/path/to/continue-session.json"
uv run --no-sync python demo/observe.py < "$export_file"
```

Set `WATCHER_URL` and a session-write `WATCHER_API_KEY`. In the Continue terminal
UI, enter `/export` and select the completed session. This writes
`continue-session-<native-id>.json` in the current directory. Pass it on stdin to
`uv run --no-sync python -m watcher_continue.integration`.

Failed delivery returns a nonzero status and a static diagnostic. This explicit
post-run step does not change native tool execution.

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

This example has no synchronous monitor. The tested Continue CLI does not deliver
the configured pre-tool hooks. Its tool overrides change descriptions or disable
tools; its `allow`, `ask` and `exclude` policies do not await an external Watcher
reply.

A custom MCP server could check its own tools, but would not control Continue's
built-in file and shell tools. Manual terminal approval is also separate from
Watcher. The public export path above remains useful for observation.

## Expected Watcher result

After a run, find `other=continue:<session-id>` in Watcher. Check the available
context, tool results and final text. Local fixtures do not verify deployed
server storage or grading.

## Limitations

Use version-one exports from a linear text conversation with completed tool outputs.
The converter rejects compaction, images, unknown roles, missing results and
incomplete or canceled tool states.

Tool results keep their stored array order; this does not promise wall-clock order.
The export contains stored messages and text context, but may omit system
instructions added separately for a model request. Subagents and branch replay
remain unverified.

Use `/export` in the terminal UI. Headless `-p --format json` prints a final reply,
not the session transcript.

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

The native test reads a file, resumes the session in the terminal UI, runs
`/export`, and submits that JSON through the SDK. It checks the initial user
context, tool result and final transcript. Conversion tests also cover call IDs
and errors.

These local tests do not verify deployed Watcher storage, real grade quality or
hosted provider behavior.

The printed output directory holds logs, installed versions and JUnit results.
`metadata.yaml` describes each mode's current test scope and versions.

## References

- [Public export command](https://github.com/continuedev/continue/blob/d3f60ba9dd3fb5bfd3c91d6fbb41ce1aa768db45/extensions/cli/src/slashCommands.ts)
- [Native JSON export writer](https://github.com/continuedev/continue/blob/d3f60ba9dd3fb5bfd3c91d6fbb41ce1aa768db45/extensions/cli/src/ui/TUIChat.tsx)
- [Session and tool-state types](https://github.com/continuedev/continue/blob/d3f60ba9dd3fb5bfd3c91d6fbb41ce1aa768db45/core/index.d.ts)
- [Native history rendering](https://github.com/continuedev/continue/blob/d3f60ba9dd3fb5bfd3c91d6fbb41ce1aa768db45/core/util/messageConversion.ts)
