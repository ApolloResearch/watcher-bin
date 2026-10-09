# LiteLLM proxy

Experimental example: a LiteLLM proxy callback that streams text as it arrives
and withholds client tool calls until Watcher permits them. Watcher parses the
provider format, applies your organization's policy and records the
conversation. This example is not an officially supported integration.

It covers the proxy's three client-facing APIs: OpenAI Chat Completions
(`/v1/chat/completions`), OpenAI Responses (`/v1/responses`) and Anthropic
Messages (`/v1/messages`), buffered or streamed, whichever provider LiteLLM
routes them to.

## How it works

1. A client calls the proxy. The callback refuses request options it cannot
   evaluate before the provider runs: `n` other than 1, Chat Completions audio, or
   Responses history stored on the provider (`previous_response_id`,
   `conversation`, `background`). A stable conversation ID is also required;
   see [Sessions and identity](#sessions-and-identity).
2. A streamed response reaches the client until its first tool call. The
   callback holds that call and subsequent content while it assembles the
   complete call and asks Watcher to evaluate it. Messages calls are complete
   at `content_block_stop`; Responses calls at `response.output_item.done`.
   Chat Completions has no per-call completion event, so its calls wait for
   the choice's `finish_reason`, including when argument fragments interleave.
3. The callback posts a non-streaming representation of the completed call
   and its context to Watcher's pre-tool-use hook with `format: "raw"`, using
   `pre_tool_use_hook(request_body=..., response_body=...)`. On subsequent
   evaluations, the previously approved response prefix is added to a copy of
   the request's assistant history. Only the new suffix call is in the
   response, so earlier calls remain context without being evaluated again.
   The request already sent to the provider is not changed.
4. An allow decision, or a deferred decision in observe mode, releases the
   call and following buffered content up to the next tool call. Evaluation
   repeats for each call, preserving stream order. A denial or escalation
   withholds the call and asks the model for an alternative. Missing decisions
   and errors stop delivery. Earlier approved calls may already have run and
   cannot be retracted.
5. Watcher records the conversation and its decisions.

Non-streaming responses evaluate each complete proposal atomically. If any
call is refused, none of that proposal's calls reaches the client. The
callback asks for an alternative and returns only an accepted proposal's
calls, with notices describing the refused calls.

The callback parses and re-encodes stream events, preserving protocol order.
Calls are released only with arguments matching the evaluated call; malformed
or inconsistent events terminate the stream. While waiting, the callback sends
keepalives as SSE comments every 10 seconds for all three APIs. These work
before the first provider event and carry no model content or tool arguments.

For streams, text after the last call and replies with no tool calls are
submitted for recording in the background. Recording does not delay stream
completion, and a recording failure does not change the delivered reply.

## Denials and alternatives

The callback can request **two alternatives** after the original proposal.
For streamed requests, each alternative also streams text immediately and
gates each tool call. The client receives one continuous response containing
approved calls and ordinary text notices with refused calls' IDs, names,
arguments and Watcher's public reasons. Denied calls are never delivered as
executable tool events. Escalations take the same path; the gateway has no
human-approval interface.

A refused provider stream is drained to complete items the client has already
seen. New, unexposed content from that proposal remains withheld.

To request an alternative, the callback appends the blocked proposal and
tool-result feedback to a copy of the provider conversation. The feedback
distinguishes withheld calls from calls already sent to the client. For an
already released call it says that execution results are unknown and the
operation must not be repeated. The caller's tool-selection constraints remain
unchanged, including forced tool choices. A forced choice can exhaust the
alternatives instead of letting the provider return a text-only refusal.

During recovery, repeating a denied or previously released operation with
the same tool name and arguments is blocked even under a new call ID. This
check lasts for the current client request. It does not equate different
commands or arguments that happen to have the same effect.

After three blocked proposals, the response ends normally with explanatory
text and any calls already approved and released. A timeout, malformed
proposal or Watcher error ends with an error instead. The callback does not
generate alternatives for missing or failed Watcher decisions.

## Prerequisites

- Python 3.12 or later and `uv`.
- A Watcher server and an API key that can monitor tool calls and write
  sessions. The server must accept the pre-tool-use hook's raw format.
- Provider credentials for LiteLLM.

## Install and configure

From this directory:

```bash
uv sync --python 3.12
.venv/bin/watcher-litellm-config > /tmp/watcher-litellm.yaml
```

Edit the `model_list` in that file for your providers, following
[LiteLLM's proxy configuration](https://docs.litellm.ai/docs/proxy/configs).
Keep `litellm_settings.callbacks: watcher_litellm.callback.watcher_callback`.
Then start the proxy with the Watcher settings in its environment:

```bash
export WATCHER_API_URL=https://watcher.example.com/api
export WATCHER_API_KEY=...
.venv/bin/litellm --config /tmp/watcher-litellm.yaml --port 4000
```

`demo/.env.example` lists these variables and the ones the packaged
configuration reads (`LITELLM_MODEL`, `PROVIDER_API_KEY`). The callback reads
the Watcher variables when it evaluates the first response, not at import. Set
up LiteLLM's own authentication and route restrictions before exposing the
proxy.

To use a released SDK wheel in another environment, install it first, then this
package with `uv pip install --python /path/to/.venv/bin/python .`.

## Sessions and identity

Every request must supply a stable conversation ID. Send
`x-watcher-session-id`, or retain valid native Claude Code session UUID or
Codex thread UUID metadata. Without either, the callback returns HTTP 400
before contacting the provider. Matching partial replies by shared text can
split one conversation or confuse independent conversations with the same
opening, so this callback does not use that fallback.

Keep the ID stable across turns and different between conversations. Sharing
an ID between users merges their conversations, so untrusted clients must not
be able to choose another user's ID. A client that cannot send the header or
native metadata needs an adapter that supplies it.

The callback stores the header value with a `litellm:` prefix, so a header of
`conversation-7` becomes the Watcher conversation ID `litellm:conversation-7`.
A header that already starts with `litellm:` is sent unchanged. Include the
prefix when you search by external ID. Without an explicit header, native
metadata produces `litellm:claude:<session-uuid>` or
`litellm:codex:<thread-uuid>`. Watcher also retains its recognized native
identity. These aliases give the session the Gateway source in the Analyzer.

For a custom Chat Completions client, replace the model with your configured
alias and reuse the header value for subsequent turns:

```bash
curl -N http://localhost:4000/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -H 'x-watcher-session-id: conversation-7' \
  -d '{"model":"your-model-alias","stream":true,"messages":[{"role":"user","content":"Hello"}]}'
```

Include the proxy's normal authentication header when it is enabled. The
conversation header identifies history; it does not authenticate the caller.

Incremental evaluations and recovery can record partial proposals and extra
trajectory branches within that session. The final delivered history is
recorded separately. Do not assume every recorded branch reached the client,
or that one client response produces exactly one stored trajectory.

The proxy key's `user_email` is sent as the developer to attribute; Watcher
honors it only for API keys allowed to attribute sessions to other users.

## Observe and enforce

The organization's `enforcement.mode` in Watcher decides the behavior; the
callback does not override it.

- **enforce**: denied or escalated calls are withheld as described above.
- **observe**: every decision comes back deferred and responses are released
  unchanged. Judgments are still recorded.
- **paused**: nothing is evaluated; conversations are recorded only.

Grading failures follow `policy_monitors.on_grading_failure`. A failure resolved
as `allow` releases tools without a completed grade; use `deny` if those must be
withheld.

## Failure behavior

- Watcher unreachable, rate limiting or returning a server error:
  HTTP 503 before streaming starts. Client SDKs may retry, which regenerates
  the model response.
- The callback's evaluation deadline expires: HTTP 504 before streaming
  starts. An earlier HTTP transport timeout is reported as HTTP 503.
- Any other Watcher error, such as a rejected API key, missing permission, a
  request too large or an exchange Watcher cannot parse: HTTP 422, which
  clients do not retry because the same request would fail again.
- A provider stream that ends early or reports an error, or provider generation
  that fails during recovery: HTTP 502 before streaming starts. Clients may retry.
- An unsupported or malformed provider response, including a complete reply
  the callback cannot combine during recovery: HTTP 422 before streaming starts.
- Once any stream has started, failures arrive as an error event in that API's
  streaming protocol. The pending call and unreleased content are withheld;
  previously released text and approved calls remain delivered. Policy denials
  and escalations instead use the bounded alternative-generation flow above.

Before any denial, each tool evaluation has a **300-second wall-clock
deadline**. It starts when evaluation begins; earlier provider generation does
not consume it. A non-streaming proposal has one deadline for its whole
evaluation.

The first denial or escalation changes the scope: the rest of recovery shares
that refused evaluation's existing deadline. Draining its provider stream,
generating both possible alternatives and evaluating their calls all consume
the remaining time. An evaluation that takes 120 seconds leaves at most
180 seconds for recovery. Alternatives do not get a fresh 300 seconds.
Expiry reports a timeout and withholds pending calls. Keepalives do not extend
either deadline.

This is separate from Watcher's own per-stage timeouts. The callback overrides
the SDK's 420-second raw-hook default and applies a total deadline in addition
to its HTTP timeout. Watcher may finish and record grading, including its
usage, after the callback times out or the client disconnects.

The callback never retries a Watcher request, because a retry can repeat billed
LLM grading.

## Limits

- Routes other than the three above, including Realtime, WebSockets, batches,
  files and LiteLLM's provider pass-through endpoints (such as `/gemini` or
  `/bedrock`), are not checked. Block them in an enforcing deployment.
- Tools that run on the provider's servers (for example hosted web search)
  execute before the response exists and cannot be prevented.
- Chat Completions tool arguments cannot be released before `finish_reason`:
  valid JSON or the start of another call does not prove that an earlier call
  will receive no more fragments. Text before the first call still streams.
- A streamed denial or error can follow an already released call. Clients must
  handle this partial outcome without assuming that no tools ran or
  automatically repeating earlier tool effects.
- Recovery adds provider generations and can add cost. The client-visible
  `usage` describes the first provider attempt, not total recovery usage.
- Non-streaming Chat recovery requires string or null content and supported
  message fields. Content arrays and populated unsupported extensions, such
  as `thinking_blocks`, return HTTP 422 when combining the original reply
  with notices and any accepted alternative. They are not silently dropped.
  Replies allowed on the first evaluation do not enter this composition step.
- Recording can contain both partial proposals and the final delivered
  history. It is not a single canonical transcript of client execution.
- Each request must carry the whole conversation. Provider-stored Responses
  history is refused.

## Tests

The local fixture suite installs the SDK and example wheels, then runs a real
`litellm` proxy between the official OpenAI and Anthropic SDK clients, a scripted
provider and a stand-in Watcher endpoint. It covers all three APIs, buffered and
streamed: allowed, denied, observe-mode and unevaluated calls, text replies,
Watcher outages, refused request options and fields forwarded to Watcher.

With Docker and `uv` installed, run from this directory:

```bash
bash tests/native/run.sh
```

The recipe downloads build dependencies, then disables external networking for
runtime tests. It prints the evidence directory and exits nonzero if a check
fails. These fixtures do not verify a deployed Watcher server or hosted models.

To exercise incremental delivery through a real local LiteLLM server without
Docker, run from this directory after `uv sync`:

```bash
litellm_evidence=$(mktemp -d /tmp/watcher-litellm-evidence.XXXXXX)
uv run pytest tests/test_incremental_proxy.py tests/test_recovery_proxy.py \
  -v -o junit_family=xunit1 \
  --basetemp="$litellm_evidence/run" --junitxml="$litellm_evidence/streaming.xml"
```

The tests start isolated HTTP provider and Watcher fixtures on free loopback
ports. They check text arriving before evaluation, withholding during grading,
release before the next evaluation, interleaved calls, keepalives, streamed
alternatives after denial or escalation, retry limits, timeouts and disconnects.
The XML's `timing_seconds`, `timeout_seconds`,
`keepalive_count` and `wire` properties retain client-observed timing and SSE
frames; the temporary directory also contains the proxy log. The fast suite
uses a two-second deadline and 0.1-second keepalives. To check the production
defaults across all three APIs, run this additional command, which
takes about 15 minutes:

```bash
WATCHER_LITELLM_TEST_DEFAULT_TIMEOUT=1 uv run pytest tests/test_incremental_proxy.py \
  -k 'grading_failure and timeout' -v -o junit_family=xunit1 \
  --basetemp="$litellm_evidence/default-timeout-run" \
  --junitxml="$litellm_evidence/default-timeout.xml"
```

Live tests in `tests/live/` use a real Watcher server and real models. They
replace the organization's managed settings with a test policy, so use a local
or disposable Watcher. Agent CLIs choose their own shell commands, some of
which go to LLM grading; give the server a triage timeout long enough for that
grading (for example `XYLON_HOOKS_TRIAGE_TIMEOUT_SECONDS=60`), or a grading
timeout withholds the call under the default grading-failure policy. They need:

| Variable | Purpose |
| --- | --- |
| `WATCHER_LIVE_API_URL`, `WATCHER_LIVE_API_KEY` | The Watcher server |
| `WATCHER_LIVE_GATEWAY_URL` | A provider gateway serving OpenAI (`/v1`), Anthropic and Vertex Gemini paths |
| `WATCHER_LIVE_GATEWAY_KEY` | The key the gateway expects, if any |
| `WATCHER_LIVE_GOOGLE_PROJECT` | The gateway's Vertex project; the Gemini route is skipped without it |
| `WATCHER_LIVE_ROUTES` | Optional subset of provider routes |

```bash
uv run pytest tests/live -v
```

`test_live_providers.py` sends a forced denied call and a forced allowed call
followed by a tool result through every provider route and all three APIs,
buffered and streamed, then reads back what Watcher recorded.
`test_live_clis.py` runs Claude Code and Codex (if installed), OpenCode and
Qwen Code (through `npx`) and Mistral Vibe (through `uvx`) through the proxy,
isolated from your own settings and hooks. It checks that an allowed file read
works and that a denied command is withheld and never runs. Live cases depend on the
model choosing the requested tool, so an occasional model refusal can fail one.

`metadata.yaml` records dated verification runs and their tested versions.
