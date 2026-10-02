# OpenClaw

Connect the embedded agent runtime in an OpenClaw Gateway to Watcher. The plugin can observe a conversation or wait for a recorded Watcher decision before a tool runs. This is an example integration, not an officially supported connector.

| Mode | What it does | Main limit |
|---|---|---|
| Observe | Sends the visible conversation after an agent turn. | It cannot stop completed tool calls. |
| Monitor | Waits for approval of the native tool call and records that decision. | Other plugins must leave the assessed arguments unchanged. |

## Install

Use OpenClaw 2026.9.4, Python 3.12 or later, uv and Node 24.16 or a compatible newer release. Its [package manifest](https://github.com/openclaw/openclaw/blob/3a9d69db306cd7f081e06254cb89c4bcc14a7107/package.json) requires Node `>=24.16.0 <25` or `>=26.1.0`.

From this directory, install the Python bridge and build the plugin package:

```sh
uv sync --project packages/python
mkdir -p dist
npm pack ./packages/node --pack-destination dist --ignore-scripts
openclaw plugins install npm-pack:./dist/watcher-openclaw-example-0.1.0.tgz --force --accept-capabilities
export WATCHER_PYTHON="$PWD/packages/python/.venv/bin/python"
export WATCHER_URL=https://watcher.example.com/api
export WATCHER_API_KEY=your-session-write-key
export WATCHER_TIMEOUT_SECONDS=60
```

Review the plugin source before installing. `--force` acknowledges a local source outside ClawHub and can replace an existing plugin with the same ID. `--accept-capabilities` accepts OpenClaw's declared plugin surface; it does not sandbox or grant the Python process's runtime permissions. The plugin starts Python and sends conversation content to your Watcher destination. Your operator's `security.installPolicy` still applies.

The Python bridge uses the SDK beside these examples. It can also be built as a wheel with `uv build packages/python`. The Node plugin does not install Python; `WATCHER_PYTHON` must name the interpreter that has the bridge and public SDK installed.

Merge the settings from `demo/observe.json` into your OpenClaw configuration. Choose `demo/enforce.json` for monitoring and observation together. Preserve existing plugin entries and allowlists. Both examples request `allowConversationAccess` because they send conversation content to Watcher.

Start the Gateway from the shell containing the exports above:

```sh
openclaw gateway run
```

For a Gateway managed as a service, provide those same environment variables to the service and restart it after installation. Shell exports do not update an already running service. With your usual model provider configured, open another terminal and send a task through that Gateway:

```sh
openclaw agent --agent main --message "List the files in this workspace." --json
```

Use the same OpenClaw configuration and state directory in both terminals. This command targets the Gateway's embedded runtime. The standalone `agent exec` path does not invoke these hooks in the tested setup.

## Observe conversations

At `agent_end`, the plugin first sends the complete supported visible conversation, including final assistant text, and waits for the SDK response. It then assesses new tool calls against their earlier history, before their results.

Observation has a 40-second work budget, plus up to two seconds to stop its checkpoint process. Each SDK request has at most ten seconds. A recording failure stops that callback before grading. If grading runs out of time, the snapshot can already be recorded while some judgments remain unfinished. A later turn resumes those checks; if there is no later turn, they can remain incomplete. A failure logs a short message and leaves the completed agent turn unchanged.

The bridge stores completed-call hashes under `~/.local/state/watcher-sdk-examples` for the Gateway's process account. Set `WATCHER_OBSERVATION_STATE_DIR` in the Gateway environment to use another writable directory. State is separated by session, Watcher destination and credential; it contains no transcript or credential text. Concurrent callbacks each attempt their snapshot, but only one grades that session at a time. A skipped grading pass resumes on a later turn.

Local progress does not detect deletion or expiry of the corresponding Watcher session or judgments. Before reimporting that history, stop the Gateway and select a new empty `WATCHER_OBSERVATION_STATE_DIR` in its environment, then restart it. The next turn retries all tool observations within the same time budget. Replaying requests does not force Watcher to replace judgments it still retains.

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

Paused bypasses and grading failures are not marked complete in the local
checkpoint; a later callback can assess them when grading is available.

Find the conversation in Watcher by its external ID, `openclaw:<session-id>`.

## Monitor tools

The hook inherits the organization's Watcher policy without settings overrides.
In enforce mode, a matching allow permits native dispatch; deny and escalation
withhold the tool. This example does not provide a human approval interface.
Valid observe or paused responses leave native permissions in control. The hook
also honors an administrator's configured allow on grading failure. Malformed,
mismatched or unavailable decisions withhold execution.

`mode="full"` selects grading depth; it does not select auto mode or override
the organization's enforcement settings. Tool names remain native, such as `exec`; configure Watcher rules for those names.

The adapter checks the exact native tool ID, name and arguments before dispatch.
At `agent_end`, monitored runs submit the final transcript without retrospective
grades replacing the earlier applied decisions.

The plugin reads history through OpenClaw's public transcript API. It refuses missing session identity or unavailable history. If the pending native tool call is not yet in the history, it adds that exact call to the request. It refuses conflicting IDs, arguments, or a call that already has a result.

Watcher has a 60-second SDK deadline. The bridge has a 65-second process deadline, and the native hook has a 70-second deadline. OpenClaw blocks tool execution when that native hook fails or times out. Operator hook settings can override its deadline. A client timeout does not stop work already running on the Watcher server.

An approved call still passes through OpenClaw's other policies. This plugin does not replace sandbox or user permission checks.

## Scope and testing

This example covers the embedded runtime served by the OpenClaw Gateway. External Codex, Copilot or ACP harnesses, channel delivery, background jobs and subagents are outside its tested scope.

Other plugins can rewrite tool arguments. OpenClaw gives ordinary tool hooks separate copies of the same input, so hook priority alone does not ensure that Watcher sees the arguments that finally execute. Use this monitor only with plugins that leave tool arguments unchanged. The native rewrite test checks this limitation explicitly.

Conversation access must be explicitly enabled. A disabled or unloaded plugin cannot monitor tools. OpenClaw's host permission rules still apply when a plugin does not load.

Text, tool calls and text results are supported. Attachments and unsupported message types are refused. While unsupported content remains in the visible history, subsequent tool checks also fail and block execution, and observation cannot record that history. Use a new supported session to resume. History access uses OpenClaw's visible transcript projection; reset, compaction and cross-harness replay need separate compatibility checks.

The tests include installed-package conversion and SDK checks. Native verification covers Linux. The native recipe uses real OpenClaw with local model and Watcher fixtures in a container with no external network. It checks actual file effects before and after approval. These fixtures do not establish deployed Watcher recording, grading quality or real provider behavior. See `metadata.yaml` for the recorded verification status.

```sh
bash tests/native/run.sh
```

Docker, Node and uv are needed to build the test environment. Dependency downloads happen before isolated execution. Test output includes logs, test results and the installed SDK version. `WATCHER_SDK_WHEEL` can select a local SDK wheel, and `WATCHER_EXAMPLE_RUN_DIR` selects the parent directory for test output.

## Directory layout

```text
openclaw/
├── metadata.yaml
├── README.md
├── packages/
│   ├── python/
│   └── node/
├── demo/
└── tests/
    ├── fixtures/
    └── native/
```

Upstream references: [tool hooks](https://docs.openclaw.ai/plugins/hooks/tool-policy) and [plugin installation](https://docs.openclaw.ai/plugins/building-plugins).
