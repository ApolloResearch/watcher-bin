# OpenAI Responses and Chat Completions

This example adds Watcher to an application that owns a native openai tool loop.
It uses the public Python clients and is not an officially supported integration.

`watcher_openai.complete` reads the native client's public raw response and sends
the original request/response JSON, endpoint and User-Agent to Watcher's hook.
Watcher converts the transcript. The wrapper returns the native response only
after every delivered function call has a matching decision for its unique
native tool-call ID. Responses is the default; pass `api="chat_completions"` for Chat Completions.

## Install and run

Use Python 3.12 or newer. From this directory:

```sh
uv sync --python 3.12
.venv/bin/python -m demo.observe
.venv/bin/python -m demo.enforce
```

Set the provider credentials, `OPENAI_MODEL`, `WATCHER_API_URL` and
`WATCHER_API_KEY` listed in `demo/.env.example` before running a demo. The scripts
read your shell environment and contact those configured services. The
Watcher key needs `sessions:ingest` to record transcripts.

The development environment uses the adjacent SDK. To install a released SDK
wheel, follow the [shared setup guide](../README.md), then install this example
into your application's environment. `pyproject.toml` declares dependencies;
`uv.lock` pins the verification environment; `uv build --wheel` builds the adapter.

## Tool execution and settings

Call `complete(provider, watcher, native_request, session_id)` with the full
native conversation and a stable, application-owned session ID. Execute only
tools returned by this function, then include their results in the next request.
The application owns both clients' lifetimes and the tool executor.

The default `enforcement="server"` follows Watcher settings. Enforce applies the
server's judgment; observe and paused preserve ordinary application permissions.
A configured grading-failure allow is honored. Explicit `enforce`, `observe` or
`paused` overrides must be permitted by administrator settings. `timeout` bounds
the Watcher request independently of provider generation.

Deny, escalation, malformed outcomes, missing decisions and transport failures
withhold the entire response. This example has no human approval interface or
automatic replanning. No provider-hosted tools are supported. Requests are
buffered and use full history; streaming and hidden provider conversation state
are rejected.

The demos append model-proposed notes to a temporary file chosen by the
application, then obtain a final answer. The enforce demo requests enforce and
requires matching allows before opening the file. The observe demo requests
observe; an underlying deny judgment does not prevent the file write. Both wait
for the hook response; neither queues background observation.

## Recording and recovery

Hook completion schedules ingestion; it is not a durable-storage acknowledgement.
Find the printed session ID in Analyzer and check tool IDs, results and the final
answer after ingestion finishes. Text-only responses also submit their real pair.

Tool results enter Watcher with the next successful provider exchange. If the
conversation stops immediately after a tool or the next generation fails, those
latest results may be absent. Keep native history in your application. Do not
rerun the whole tool loop after an uncertain result: completed file writes cannot
be undone by a later monitoring failure. The wrapper does not fabricate provider
responses to flush results.

## Development and verification

```sh
env -i PATH="$PATH" ../run-without-network.sh "$PWD/.venv/bin/python" \
  -m pytest --noconftest -c pyproject.toml tests
```

The Linux wrapper needs permission to isolate network access. Tests exercise the
native provider client and public Watcher SDK using local HTTP responses. They
cover exact wire preservation, unique call-ID checks, effective modes,
whole-response withholding, malformed output, real file effects and full native
continuation. They do not establish hosted-provider behavior, real grade quality
or deployed Watcher storage.

The wrapper is in `src/watcher_openai/`. `demo/app.py` owns the tool loop and the
two small entry points select a mode. `tests/` holds fixtures and behavior checks.
`metadata.yaml` records tested versions and scope. To verify packaging, install
the SDK and adapter wheels in a fresh environment and run copied `demo/` and
`tests/` outside the checkout, without an editable install or `src/` on PYTHONPATH.

Buffered text-only replies stopped by an output limit or content filter are
submitted and delivered unchanged. Incomplete responses containing tool proposals
are withheld in every mode; the integration never executes a partial proposal.
