# Mistral AI: monitored application tools

This example connects the native Mistral AI Python client to Watcher. Use it in an
application that owns its tool loop. It is a reference example rather than an
officially supported integration.

`Monitor` checks each buffered tool batch before invoking your registered async
functions. It follows your Watcher settings: enforce applies allow, deny or
escalate; observe and paused preserve your application's ordinary tool dispatch.
A configured grading-failure allow is honored. An escalation blocks because this
example has no human approval interface.

The adapter sends the original provider request and complete response to the
public SDK hook endpoint. Watcher converts the transcript. The local adapter
checks unique native tool IDs so a missing decision cannot
release a function. It does not define another transcript format.

## Install and configure

Use Python 3.12 or newer. From this directory:

```sh
uv sync --python 3.12
```

This development environment uses the adjacent SDK source. To use a released
SDK wheel, follow the [shared setup guide](../README.md). `pyproject.toml` and
`uv.lock` declare package and test dependencies. `uv build --wheel` builds this
example for installation in your application environment.

Set `PROVIDER_API_KEY`, `PROVIDER_BASE_URL`, `PROVIDER_MODEL`, `WATCHER_API_KEY`
and `WATCHER_BASE_URL` as shown in `demo/.env.example`. The demos read your shell
environment. They send their sample prompts to those configured services.
Recording requires a Watcher key with `sessions:ingest`; hook completion alone
is not a durable-storage acknowledgement.

Use `async with make_client(...) as provider`. This context installs a public HTTPX response hook, preserves existing hooks and closes its own transport. If you supply an HTTPX client, you remain responsible for closing it; do not share it with another simultaneous client context.

## Run synchronous monitoring

```sh
.venv/bin/python demo/enforce.py
```

The demo asks for weather, waits for Watcher, calls its local demonstration
function and supplies that result to the next model turn. Set the server to
enforce to prevent refused tools. The monitor inherits server settings by
default; an explicit `enforcement` override may be rejected by administrator locks.
`WATCHER_TIMEOUT` bounds grading and defaults to 420 seconds.

Import `Monitor` and `run_turn` from `watcher_mistralai.monitoring` in your
application. Pass declarations as `tools` and async implementations as
`functions`. Every function in the batch must be registered and every delivered
call must have a matching decision before any callback starts. Keep the same
monitor and pass the returned full native history into the next turn.

Transport failures, malformed outcomes, denied calls and unhandled escalations
raise without starting the batch. Ordinary callback errors become linked native
tool results. The monitor does not retry tool execution or grading. It rejects
reused call IDs within one instance; this state does not survive a restart.

## Run background observation

```sh
.venv/bin/python demo/observe.py
```

`Observation` and `complete` in `watcher_mistralai.integration` provide a
separate observation path that returns the provider response without waiting for
grading. It inherits Watcher's configured mode, including paused. Returned
decisions are advisory because this path has already released the model response;
it does not block or reverse an action. Paused and grading-failure fallback
outcomes do not count as completed judgments.

In Enforce mode, Watcher can store a retrospective assessment as an applied
denial and count it in automatic-denial totals after the tool has run. Those
records describe the assessment; they do not show that execution was prevented.

Stop producers, call `await observation.flush()`, and inspect `error_count`,
`errors` and `judgments`. The queue holds at most 32 pending pairs, reports dropped
work, and retains the latest 128 errors and outcomes. It is not durable.

## Transcript completeness and limits

Use one application-owned conversation ID and full native history for every
turn. Tool results enter Watcher with the next real provider request/response
pair. If generation fails or the conversation stops immediately after a tool,
its latest results may not be in Watcher. Retain native history in your
application; do not rerun completed tools to recover an upload. The example does
not invent a provider response to flush a final tool result.

Find the printed conversation ID in Analyzer. Check the proposed tools, their
results and the final answer after ingestion completes. A successful hook call
schedules ingestion; it does not prove that a session was stored.

Only buffered, application-executed function tools through this wrapper are
covered. Streaming, provider-hosted tools, hidden provider conversation state
and other clients are outside its scope. Model generation itself happens before
the tool gate. This is an application integration, not a gateway plugin.

## Test and package

```sh
env -i PATH="$PATH" ../run-without-network.sh "$PWD/.venv/bin/python" \
  -m pytest --noconftest -c pyproject.toml tests
uv build --wheel
```

The Linux wrapper requires permission to create an isolated network namespace.
Tests exercise the installed native provider library and public Watcher client
with local HTTP replies. They check exact transmitted JSON, effective policy,
whole-batch withholding, callback effects, native history, missing decisions,
queue limits and ID reuse. These fixtures do not establish hosted-provider
behavior, real grading quality or deployed Watcher persistence.

`src/` holds the installable adapter; `demo/` shows application use; `tests/`
contains the local fixtures and behavior checks. `metadata.yaml` records versions,
verification scope and limitations. Tests can also run against an installed wheel
outside the source checkout.

Buffered text-only replies stopped by an output limit or content filter are
submitted and delivered unchanged. Incomplete responses containing tool proposals
are withheld in every mode; the integration never executes a partial proposal.
