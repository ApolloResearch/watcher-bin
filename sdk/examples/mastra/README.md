# Mastra: observation and synchronous native tool monitoring

This example has a Node adapter and a Python bridge. Install both. The Node
adapter runs Mastra's `Agent.generate` and converts its messages to Inspect chat
messages. The bridge calls the public Watcher SDK.

The native pre-tool integration follows Watcher's enforce, observe or paused
setting. A separate completed-history observer is also available. This is an
experimental example, not an officially supported integration.

## Scope

**Observation** captures complete step snapshots, including parallel tool calls,
linked results and the final assistant message. Running the Python bridge afterward
records them and grades each tool identity once. It cannot prevent an executed tool.

**Enforcement** uses Mastra's `processOutputStep` before any registered tool
callback runs. Each pending call needs a matching applied policy result. Just before
execution, the callback checks the call ID and arguments again and consumes
that permission. It does not control tools hosted by the provider or other agents.

## Prerequisites and permissions

Use Node 22.13 or newer, Python 3.12 and `uv`. The Node packages are
`@mastra/core` 1.66.0, AI SDK 6.0.182 and Zod 4.6.5. The Python component
uses the adjacent Watcher SDK source directory.

Live demos also require a provider model and credential, plus a Watcher key with
session-write permission. Both synchronous monitoring and the
post-run observer inherit server policy. Paused mode records history without
grading; post-run decisions are advisory to actions that already finished.
Local fixture tests need no provider credentials.

In Enforce mode, Watcher can store a retrospective assessment as an applied
denial and count it in automatic-denial totals after the tool has run. Those
records describe the assessment; they do not show that execution was prevented.

## Install the two components

From this example directory:

```sh
uv sync --project packages/python
mkdir -p dist
npm pack ./packages/node --pack-destination dist --ignore-scripts
npm install --no-save --package-lock=false --ignore-scripts dist/watcher-mastra-example-0.1.0.tgz
export WATCHER_PYTHON="$PWD/packages/python/.venv/bin/python"
```

The Node tarball contains its runtime code but does not install Python. Set
`WATCHER_PYTHON` to an absolute path where `watcher_mastra_bridge` and the
Watcher SDK are installed. The Node adapter calls
`python -m watcher_mastra_bridge.gate`, not a sibling source file. Install both
the Node package and Python wheel when adding the adapter to an application.

## Configure

Use `demo/.env.example` as a list of settings; export your own values in the shell.
The demos do not automatically load that file. Set `PROVIDER_MODEL` to a Mastra
provider/model string and the corresponding provider credential, for example
`OPENAI_API_KEY`. Set `WATCHER_BASE_URL`, `WATCHER_API_KEY` and a fresh
`WATCHER_SESSION_ID` for the conversation. `WATCHER_TIMEOUT` defaults to 420 seconds
for a full synchronous grade. Credentials and transcripts should remain private.

## Observation example

Choose a fresh empty `SNAPSHOT_DIR`, then run:

```sh
node demo/observe.mjs
packages/python/.venv/bin/watcher-mastra-observe
```

The native agent requests weather for Paris and Tokyo and writes numbered snapshots.
The weather callback returns demonstration values; it does not query a weather service.
The bridge submits snapshots in order and judges each tool with the historical prefix
through its assistant call message, in batches of at most 32. It then records the full
snapshot, including after a monitoring failure. A nonzero bridge exit reports incomplete
recording or grading. Tool execution happens before this bridge runs.

For an application, import `run` or `transcript` from
`watcher-mastra-example/observation`; import `observe_snapshots` from
`watcher_mastra_bridge` to submit caller-ordered snapshot files.

## Synchronous monitor example

After setting the Watcher and provider configuration above, run:

```sh
node demo/enforce.mjs
```

Import `runMonitored` from `watcher-mastra-example/monitoring`. Replace the demo's
weather callback with your tool. The native processor sends the full pending
history through the installed Python SDK.

The Python gate applies the server's decision before native dispatch:

| Watcher result | Native behavior |
| --- | --- |
| Enforce: allow | Continue ordinary tool execution, including an administrator-configured grading-failure allow. |
| Enforce: deny | Abort the pending native step before any registered tool runs. |
| Enforce: escalate | Await the application's human approval callback, or abort when none is supplied. |
| Observe or paused: deferred | Preserve ordinary native execution and permission checks. |

Missing/mismatched identities, invalid results, transport failures and failure to
start Python withhold the pending batch. The adapter does not retry grading or
execution. Other native validation and permission checks still apply.

`runMonitored(model, executeWeather, sink?, inputSchema?, options?)` accepts a Zod schema.
Object key order does not matter, but the schema must keep the model's JSON values.
Use explicit values rather than adding defaults.

Defaults, removed fields and transforms that change values are recorded and refused
before grading. Invalid schema inputs are refused before a Watcher request.
Results are saved after each completed native step, even one that uses the last
step in the budget. The adapter does not invent a final answer.

## Human approval and unattended use

The supplied demo has no approval callback, so unattended agents stop on escalation.
To include a human, pass `{ approve }` as the fifth argument to `runMonitored`.
`approve(request)` must await an authorized person's decision and return literal
`true` or `false`. It receives `tool_use_id`, `tool_name`, a copy of `tool_input`,
and the public Watcher `outcome`. Connect it to your application's approval UI or
queue; the example does not include one or run an automatic approval model.

The local Python sidecar verifies that the choice belongs to the pending call,
waits for the original escalation record, uploads the human choice and reads back
the stored human choice and pending/blocked status. Only then does approval permit execution. Original
grades and escalation remain intact. Approval records a pending execution;
rejection records blocked. This requires findings and content access and permission to
update the session as its owner or with `sessions:write:any`.
For a service API key, configure `sessions:ingest`, `sessions:findings:read:any`,
`sessions:content:read:any` and `sessions:write:any` for transcript recording and human-decision reporting.
Upload/readback failures, including an acknowledged content-scrub no-op, block
the call.

The callback can wait while the native step is held, but process state is not a
durable approval queue. Persist decisions separately when crash recovery is needed.
Do not restart a tool to retry a failed audit upload.

## Expected Watcher result

Find `WATCHER_SESSION_ID` as an external ID in Analyzer. In observe mode, check
both tool IDs, actual results and final text. In enforce mode, check decisions
before approved tools run, then their recorded results and final message.

A successful hook response confirms evaluation or request acceptance, not durable
storage; recording happens asynchronously. Query the session to verify stored
messages and decisions. Paused mode intentionally submits history without grading.
A saved transcript alone does not prove its tools were graded.

The live demos use your configured services. Tests use real Mastra and the
installed SDK with local model and Watcher replies. They do not verify storage
or grade quality on a deployed server.

## Limitations

This is an experimental example, not an officially supported integration.
Observation requires a separate bridge invocation; snapshots contain conversation
data and need a private directory and retention policy.

Snapshots contain full history. There is no incremental ingestion, durable
queue, durable execution ledger or recovery across process restarts. The bounded
observation queue preserves ordering, counts failures and drops new submissions
visibly when full. Call `flush()` after producers stop.

Unsupported native content, unlinked tool messages, null arguments and duplicate
results fail visibly. Tool failures retain linked Inspect error markers. The monitored
agent controls only its registered client tools, with schemas preserving model values.

## Tests

Run the complete test suite from this directory:

```sh
bash tests/native/run.sh
```

The runner builds the SDK and adapter packages, installs them in a fresh
environment, and tests them outside the source checkout. Package downloads finish
before the tests start. `WATCHER_SDK_WHEEL` can select a prebuilt SDK wheel.
`WATCHER_EXAMPLE_RUN_DIR` selects a parent for a fresh output directory.

The Linux wrapper needs noninteractive `sudo`, `unshare`, `setpriv` and `ip`.
It permits only loopback traffic. Provider and Watcher replies come from local
fixtures. The tests do not use your service credentials.

Node tests check native messages and tool-error conversion. Python tests check
the queue, messages at each call, argument identity, inherited policy and the
application approval exchange, including failed human-audit uploads.

Tests that run the native agent and SDK together check actual file writes. No
write occurs while a decision is pending or on deny/error replies. Allowed calls
preserve IDs, results and final history. These local tests do not verify deployed
Watcher storage, real grade quality or hosted provider behavior.

Prepare the installed image for Watcher API/database verification with:

```sh
bash tests/native/build.sh
```

This recipe requires Linux x86_64, Python 3.12+, uv, Docker and package-registry
access. It accepts `WATCHER_SDK_WHEEL` and `WATCHER_EXAMPLE_RUN_DIR`, creates a fresh
output directory, and writes `image.id`, package checksums and source-comparison
receipts there. It prepares artifacts without starting an agent; the Watcher
backend runner launches the image separately with networking disabled.

The build uses a checksum-verified Node 24.11.1 archive and the committed npm
lockfile. Package lifecycle scripts are disabled during installation.

The printed output directory holds logs, installed versions and JUnit results.
`metadata.yaml` describes each mode's current test scope and versions.
