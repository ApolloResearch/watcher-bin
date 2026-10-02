# Goose: native lifecycle integration

Native Stop/export transcript with tool IDs, results and final text.

The maintained upstream is [aaif-goose/goose](https://github.com/aaif-goose/goose); the former `block/goose` repository redirects there. The native fixture uses its [v1.50.0 release](https://github.com/aaif-goose/goose/releases/tag/v1.50.0).

**How it works.** The Stop plugin runs
`goose session export --session-id ID --format json` and converts the exported
conversation to Inspect messages. It uses the native session's external ID to
grade completed tools and save the final history through the public SDK.

Generate `plugin.json` and `hooks/hooks.json` in a new plugin directory. Register
that directory through Goose's normal plugin config. Observation does not block
tools. Capture and delivery are separate, so SDK errors cannot change tool output.

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
uv run --no-sync watcher-goose-observe-settings > /tmp/watcher-goose-observe.json
```

Generate the matching plugin manifest with `uv run --no-sync watcher-goose-plugin-manifest > /tmp/watcher-goose-plugin.json`. Place that manifest at `plugin.json` and the rendered hook settings at `hooks/hooks.json` in a fresh plugin directory. Add this directory using the normal Goose plugin configuration, preserving existing entries.

The command prints settings; it does not install hooks or change their deadlines.
Use the steps below to load the file. Keep the Python environment at its current
path. The command fills `__WATCHER_PYTHON__` in the templates under `demo/`;
do not install a template with that marker still in it.

Set `WATCHER_URL` and a session-write `WATCHER_API_KEY` where the hook process
can read them. Load the generated plugin and start Goose in a test workspace.
Keep normal auth and monitoring in place. After the run, find
`goose:<native-session-id>` in Watcher and check final text and available results.
Delivery to a deployed Watcher server remains unverified.

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
`Stop` 30 seconds in total. Exporting the native history has its own 10-second
timeout and uses part of that same 30-second budget before grading starts.

Each completion waits for historical tool checks one at a time before the final
save. The outer deadline can stop the process before that save finishes. Newest
tool results or final text can then remain unrecorded, even if earlier prefixes
reached Watcher. Trying the final save after a grading error does not protect it
from the whole process being stopped.

A longer outer deadline gives more time but does not guarantee a final save.
Treat a timeout as incomplete observation. Server work may still finish and be
billed; the adapter does not retry. The local tests do not verify deployed latency.

## Synchronous monitoring

Generate the pre-tool configuration. The same loaded hook follows the Watcher
organization's enforce, observe or paused mode; it sends no settings override.

```sh
uv run --no-sync watcher-goose-enforce-settings > /tmp/watcher-goose-enforce.json
```

Use `/tmp/watcher-goose-enforce.json` as the test plugin's `hooks/hooks.json`.
It adds `PreToolUse` and keeps `Stop` export as a transcript-only submission.
Completed calls are not regraded and the final submission does not request an
observe override.

In enforce mode, a matching allow lets native dispatch continue. This includes an
administrator-configured allow on a grading failure. Deny and escalation block;
this hook does not provide a human approval interface. In observe or paused mode,
a valid deferred result preserves Goose's ordinary dispatch and permissions.
Mismatched identities, malformed outcomes, inconsistent policy provenance and
network errors withhold the tool. This path uses `mode="full"` for grading depth.

The separate observation-only configuration still uses historical `triage_only`
grades at Stop. Select the pre-tool configuration when you want one policy boundary
that can observe or enforce according to server settings.

The SDK deadline defaults to 420 seconds and can be reduced with `WATCHER_TIMEOUT_SECONDS`. Native command/plugin deadlines allow additional time around that request. A timeout does not cancel server-side grading or its cost, and the example never retries automatically.

## Expected Watcher result

After a run, find `other=goose:<session-id>` in Watcher. Check the available
context, tool results and final text. Successful hook responses confirm evaluation
or request acceptance, not durable storage: recording happens asynchronously.
Recording needs session-write permission. Use public readback to verify it.
Local fixture responses alone do not prove real server persistence or grading.

## Limitations

Native tests run shell tools and Stop/export hooks in Goose 1.50.0 with local
replies. They do not prove deployed storage or real grading. The converter keeps
parallel IDs and available results and rejects unknown content.

Subagents, compaction and branch replay are outside the tested scope. Your
application owns retries and retention after a delivery failure.

**Failure behavior.** The hook sets Goose's `on_failure: "block"`. Spawn errors,
crashes, malformed output and native timeouts therefore block execution too.
A bad plugin configuration or matcher can prevent the hook from loading at all;
check installation with the native test recipe.

Goose's [hook protocol](https://block.github.io/goose/docs/guides/context-engineering/hooks/#blocking-a-tool-call)
states that exit `0` with `{"decision":"allow"}` allows the hook chain to
continue. It does not record an approval choice in Goose's tool permissions.
The example leaves the other permission checks and policy hooks in place.
The converter handles linear visible text and native MCP calls/results directly;
IDs must be unique and results must match unanswered calls. Attachments, internal
provider content, compaction and branch replay are outside the supported scope.

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

- [documentation/docs/guides/context-engineering/hooks.md](https://github.com/aaif-goose/goose/blob/50666ae0b9a51e260b52b7efbab2e4e020346e94/documentation/docs/guides/context-engineering/hooks.md)
- [crates/goose-cli/src/cli.rs](https://github.com/aaif-goose/goose/blob/50666ae0b9a51e260b52b7efbab2e4e020346e94/crates/goose-cli/src/cli.rs)
- [crates/goose-provider-types/src/conversation/message.rs](https://github.com/aaif-goose/goose/blob/50666ae0b9a51e260b52b7efbab2e4e020346e94/crates/goose-provider-types/src/conversation/message.rs)
- [crates/goose-provider-types/src/conversation/tool_result_serde.rs](https://github.com/aaif-goose/goose/blob/50666ae0b9a51e260b52b7efbab2e4e020346e94/crates/goose-provider-types/src/conversation/tool_result_serde.rs)
