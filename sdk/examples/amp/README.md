# Amp: native lifecycle integration

Public Amp Python SDK execute stream after completion; service-backed native CLI completion is unverified.

**What it does.** Install `amp-sdk==0.1.20260823161440` and the official Amp CLI.
Call `await run_amp(prompt, cwd, client)` to consume the public execute stream.
It keeps user, assistant and tool blocks and rejects subagent streams.

The adapter converts captured activity to Inspect messages. It grades completed
tools and saves the final transcript. It cannot block tools. Capture and delivery
are separate, so SDK errors cannot change tool output.

Full execution with the real Amp service remains unverified.

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

Set `PROMPT`. From the disposable workspace, invoke the demo with the installed environment:

```sh
/absolute/path/to/example/.venv/bin/python /absolute/path/to/example/demo/observe.py
```

This intentional run needs native provider/service credentials; it is separate from isolated tests.

Set `WATCHER_URL` and a session-write `WATCHER_API_KEY`. The library accepts
an `AsyncWatcherClient`; use it as an async context manager. Start in a test
workspace and keep your normal permissions and monitoring in place. After the
run, find `other=amp:<native-session-id>` in Watcher and check the final text
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

Synchronous monitoring is not implemented by this example. The Amp Python SDK
can configure a command through `create_permission(tool, "delegate", {"to": command})`
in `amp.permissions`. This example does not implement the delegate command or verify its native input
and decision protocol.

The protocol, pending call IDs, context and failure handling need native tests.
The CLI diagnostic stops at Amp service startup before tools or permission hooks.
The observer cannot block tools. This missing proof does not mean that Amp cannot
support a pre-tool Watcher check.

## Expected Watcher result

After a run, find `other=amp:<session-id>` in Watcher. Check the available
context, tool results and final text. Local fixtures do not verify deployed
server storage or grading.

## Limitations

Tests do not cover real Amp tools or a deployed Watcher server. The converter
keeps parallel call IDs and available results. It rejects unknown content.
Subagents, compaction and branch replay are outside the tested scope. If saving
fails, your application must handle retries and keep any data it needs.

## Tests

Run the adapter tests from this directory:

```sh
../run-without-network.sh "$PWD/.venv/bin/python" -m pytest --noconftest -c pyproject.toml
```

The Linux wrapper needs `sudo`, `unshare`, `setpriv` and `ip`. It runs with only
loopback networking and a fresh home. These tests check the converter, bridge process and SDK HTTP requests. They also
run the real Amp Python SDK with a fixture CLI process. That test parses streamed
user, assistant, tool and final-result messages. It does not run real native tools.

Native execution and delivery to a deployed Watcher server remain unverified.
`metadata.yaml` lists the tested versions and scope for each mode.

Run `bash tests/native/diagnose.sh` with Docker and `uv` to check the CLI's
service prerequisite. The CLI runs in a container with no network. The check
expects Amp service startup to fail before any tool or permission callback.
A passing diagnostic is not a successful native integration test.

`AMP_URL` points to the Amp service. It is not an OpenAI-compatible model URL.
Custom provider setup needs an account or workspace, and headless runs need an
Amp token. A local model server cannot supply the Amp service API on its own.
Native tests need a service implementation or an authenticated Amp run.

## References

- [Official SDK/hook reference](https://ampcode.com/docs/markdown/sdk/python).
