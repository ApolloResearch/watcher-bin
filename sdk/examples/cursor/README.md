# Cursor: native lifecycle event collection

Partial event-journal context from documented hooks; native dispatch is unverified.

**How it works.** Add the generated observe settings to `.cursor/hooks.json`
in a trusted test project. Generic hooks cover Shell, Read, Write and MCP tools.
A private SQLite journal stores prompts, tool calls, results and final text.

At completion, the adapter converts those events to Inspect messages and sends
the full observed history through the public SDK. Parallel calls keep native IDs.
Repeated deliveries converge; conflicting IDs are rejected. The adapter grades
tools after they have run, as described below.

## Installation and configuration

Use Python 3.12+, `uv`, and an existing native harness installation with its normal credentials. From this directory:

```sh
uv sync --no-editable
```

The development environment uses the adjacent Watcher SDK source directory.
`pyproject.toml` lists the package version, dependencies and commands. `uv.lock`
records the tested environment. Once installed, the adapter uses installed
packages; it does not need the source checkout at runtime.

Set `WATCHER_URL` and a session-write `WATCHER_API_KEY`. Both modes also need
`WATCHER_STATE_DIR`, a private persistent directory for the event journal.
Keep it across resumed sessions. `demo/.env.example` lists these settings but
is not loaded for you. Keep your normal permissions and monitoring hooks.

## Observation

Generate observation settings for the installed Python environment:

```sh
uv run --no-sync watcher-cursor-observe-settings > /tmp/watcher-cursor-observe.json
```

The command prints settings; it does not install hooks or change their deadlines.
Use the steps below to load the file. Keep the Python environment at its current
path. The command fills `__WATCHER_PYTHON__` in the templates under `demo/`;
do not install a template with that marker still in it.

Use the generated settings in a test project. Their commands already point to
the installed Python environment. Keep normal auth and monitoring, and do not
overwrite an existing hook file. The state directory contains session data;
keep it private and retain it across resume.

Observation errors print static diagnostics. The hooks return these values even
if recording fails:

| Hook | Output |
| --- | --- |
| `preToolUse` | `{"permission":"allow"}` |
| `beforeSubmitPrompt` | `{"continue":true}` |

Cursor's [preToolUse reference](https://cursor.com/docs/hooks#pretooluse)
defines `permission: "allow"` as "to proceed" and `"deny"` as "to block";
`"ask"` is accepted by the schema but not enforced for this hook. The example
uses that documented protocol. Its interaction with Cursor's own confirmation
prompts remains unverified.

Malformed input exits 1. Cursor documents nonzero exits other than 2 as allowing
execution by default. Keep that behavior for the observation-only hook.

Each SDK request has 10 seconds; one completion may send several requests. To check
live delivery, run two tools and a final answer, then find
`cursor:<native-session-id>` in Watcher and inspect all three stages.

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

Generate the pre-tool configuration. The hook follows the Watcher organization's
observe, enforce or paused setting.

```sh
uv run --no-sync watcher-cursor-enforce-settings > /tmp/watcher-cursor-enforce.json
```

**Pre-tool check.** The enforce settings replace only `preToolUse` with
`watcher_cursor.pre_tool`; all other observation hooks stay in place. It saves
the pending ID in the journal, then calls the public SDK in full grading mode.

The hook inherits the organization's Watcher policy without settings overrides.
In enforce mode, a matching allow permits native dispatch; deny and escalation
withhold the tool. This example does not provide a human approval interface.
Valid observe or paused responses return the documented `permission: "allow"`. The hook
also honors an administrator's configured allow on grading failure. Malformed,
mismatched or unavailable decisions withhold execution.

`mode="full"` selects grading depth; it does not select auto mode or override
the organization's enforcement settings.

A withheld call returns `permission: "deny"` with exit 2. Model context is partial because some instructions are absent
from the hook events. The SDK wait defaults to 420 seconds and the native hook
timeout is 480 seconds. Native startup, crash and deadline behavior are unverified.

The CLI diagnostic stops at login before any native callback. Tests check SDK
replies and the adapter's refusal output. They do not check native execution,
startup, crashes, real grades or deployed storage. To test the native path, use
an authenticated Cursor service session.

## Expected Watcher result

After a run, find `other=cursor:<session-id>` in Watcher. Check the available
context, tool results and final text. Local fixtures do not verify deployed
server storage or grading.

## Limitations

Install all required hooks before a conversation starts. Hooks expose only part
of the model context; system prompts and intermediate content may be missing.
Detached callbacks can arrive out of order. The adapter rejects a result that
has no matching call.

The journal is not a full model transcript. Tests do not verify Cursor's native
hook dispatcher or a deployed Watcher server, so native enforcement remains
unverified.

## Tests

Run the adapter tests from this directory:

```sh
../run-without-network.sh "$PWD/.venv/bin/python" -m pytest --noconftest -c pyproject.toml
```

The Linux wrapper needs `sudo`, `unshare`, `setpriv` and `ip`. It runs with only
loopback networking and a fresh home. These tests check the converter, bridge
process and SDK HTTP requests. They do not run the native hook dispatcher.

Native execution and delivery to a deployed Watcher server remain unverified.
`metadata.yaml` lists the tested versions and scope for each mode.

Run `bash tests/native/diagnose.sh` with Docker, curl and Python 3 to check CLI
authentication. It installs the official CLI in a container with no network or
host credentials. The check expects an unauthenticated state and no hook delivery.
A passing diagnostic is not a successful native integration test.

The standalone CLI supports hooks without an IDE. It needs an account login or
`CURSOR_API_KEY`. `--endpoint` points to the Cursor API, not a documented
OpenAI-compatible local model endpoint.

Even bring-your-own-key traffic uses Cursor's servers. Native tests therefore
need an authenticated service run.

## References

- [Official hooks documentation](https://cursor.com/docs/agent/hooks).
