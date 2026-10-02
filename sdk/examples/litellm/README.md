# LiteLLM proxy

Experimental example: a LiteLLM proxy callback that holds each model response
until Watcher has judged the tool calls in it. The callback sends the client's
request body and the provider's response to Watcher unchanged; Watcher parses
the provider format, applies your organization's policy and records the
conversation. This example is not an officially supported integration.

It covers the proxy's three client-facing APIs: OpenAI Chat Completions
(`/v1/chat/completions`), OpenAI Responses (`/v1/responses`) and Anthropic
Messages (`/v1/messages`), buffered or streamed, whichever provider LiteLLM
routes them to.

## How it works

1. A client calls the proxy. The callback refuses request options it cannot
   evaluate before the provider runs: more than one choice (`n > 1`), or
   Responses history stored on the provider (`previous_response_id`,
   `conversation`, `background`).
2. The provider responds. A streamed response is buffered until complete.
3. The callback posts the request body, the complete response and the endpoint
   path to Watcher's pre-tool-use hook with `format: "raw"`, using the SDK's
   `pre_tool_use_hook(request_body=..., response_body=...)`. Watcher returns a
   decision for every new client tool call, identified by the call's ID.
4. The response is released unchanged only if every client tool call in it
   has an allow decision, or a deferred one in observe mode. If any call is
   denied, escalated, could not be evaluated or received no decision, the
   callback removes **all** client tool calls from that response and adds a
   text explanation, so the client gets an ordinary reply and runs nothing.
   Tool calls in one response often depend on each other, so running only
   some of them is not offered.
5. Watcher records the conversation and its decisions.

Streamed responses are re-encoded from the evaluated body instead of replaying
the provider's chunks, so the client can only execute exactly what Watcher saw.
The re-encoded stream carries the same content in the standard event sequence
for its API, but not provider-specific extras such as per-chunk timing.

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
export WATCHER_API_URL=https://watcher.example.com
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

Claude Code and Codex requests normally carry their own session IDs, and
Watcher groups each conversation by them. Requests from other applications
carry no session ID. That includes OpenCode, Qwen Code and Mistral Vibe, even
though Watcher recognizes those agents. For these, send an
`x-watcher-session-id` header with a stable ID per conversation; without one,
Watcher groups requests by their shared conversation history. Qwen Code and
Mistral Vibe cannot send the header. Sharing an ID between users merges their
conversations, so untrusted clients must not be able to choose another user's
ID.

The callback stores the header value with a `litellm:` prefix, so a header of
`conversation-7` becomes the Watcher conversation ID `litellm:conversation-7`.
A header that already starts with `litellm:` is sent unchanged. Include the
prefix when you search by external ID. The Analyzer shows sessions with this
prefix under the Gateway source only when an ID follows the prefix, so a header
of exactly `litellm:` shows Hooks API. For requests without the header, the callback
sends no conversation ID, so their sessions show the Hooks API source instead,
even when a native session ID groups them. Send the header to get the Gateway
source.

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

- Watcher unreachable, timing out (240 seconds by default), rate limiting or
  returning a server error: the client receives HTTP 503 and no part of the
  response. Client SDKs may retry, which regenerates the model response.
- Any other Watcher error, such as a rejected API key, missing permission, a
  request too large or an exchange Watcher cannot parse: HTTP 422, which
  clients do not retry because the same request would fail again.
- A provider stream that ends early or reports an error: HTTP 502, which
  clients may retry.
- A provider stream in a shape the callback does not interpret: HTTP 422.

The callback never retries a Watcher request, because a retry can repeat billed
LLM grading.

## Limits

- Routes other than the three above, including Realtime, WebSockets, batches,
  files and LiteLLM's provider pass-through endpoints (such as `/gemini` or
  `/bedrock`), are not checked. Block them in an enforcing deployment.
- Tools that run on the provider's servers (for example hosted web search)
  execute before the response exists and cannot be prevented.
- Streaming is buffered: clients see nothing until Watcher has decided.
- When calls are withheld, the next request from the client contains the
  explanation instead of the calls, so Watcher records it as a new branch of the
  same conversation. Without `x-watcher-session-id` or a native session ID,
  that request starts a new session instead.
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

`metadata.yaml` records the latest tested versions and results.
