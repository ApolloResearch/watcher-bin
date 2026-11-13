# LiteLLM proxy

Experimental example: a LiteLLM proxy callback that streams text as it arrives
and withholds client tool calls until Watcher permits them. Watcher parses the
provider format, applies your organization's policy and records the
conversation. Operators integrate this example into their own LiteLLM build;
the native Copilot configuration and tested versions are described below.

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
   repeats for each call, preserving stream order. A denial withholds the
   call and asks the model for an alternative; an escalation withholds it and
   asks the model to put the decision to the user. Missing decisions and
   errors stop delivery. Earlier approved calls may already have run and
   cannot be retracted.
5. Watcher records the conversation and its decisions.

Every covered request also gets a fixed system notice before it reaches the
provider. See [The system notice](#the-system-notice).

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
approved calls and ordinary text notices. Each notice names a refused call
with its arguments and Watcher's public reason, starts with `WATCHER NOTICE`
(a denial) or `WATCHER ESCALATION`, and says that Watcher added it rather
than the model. Refused calls are never delivered as executable tool events.

The model learns about a denial from its proposed call's tool result:
Watcher blocked the call, the reason, and an invitation to continue the
user's task another way, because Watcher checks every call. It is not
offered a text-only "explain why you cannot continue" reply: a reply with no
tool call ends the agent's turn, since agent harnesses only call the model
again after tool results or user input.

An escalation is not retried. The gateway has no human-approval interface,
so it makes **one final generation** in which the escalated call's tool
result asks the model to stop and ask the user whether to allow the call,
with labelled options. The model writes that question itself, so on the
next turn it reads its own words rather than a question the gateway put into
its reply. The same final generation follows a third blocked proposal,
asking the model to say what was blocked and ask how to proceed. Any call
the final generation proposes anyway is withheld without evaluation, and a
fixed question to the user follows the reply's text. The same fixed question
is added when the reply has no text or was cut off (token limit, content
filter), and it replaces the reply when the final generation fails or runs
out of time. Either way the response then ends normally rather than as cut
off. When streaming, the final reply is read in full before any of it is
sent, so a failure partway through still ends with the fixed question.

Only escalations decided by Watcher's graders (`decision_source` of
`policy_gateway` or `triage`) offer to allow the call, and only when no other
escalation in the same response is held by policy: if the user allows
it, the model proposes it again and Watcher grades it again, with the user's
answer in the conversation. A rule, a tool threshold or the grading-failure
policy decides without reading the conversation and would escalate the same
call again, so for those escalations the notices say the call cannot be
approved in the conversation, and the model offers to skip it, do something
else, or ask an administrator to change the policy.

A refused provider stream is drained to complete items the client has already
seen. New, unexposed content from that proposal remains withheld.

To request an alternative, the callback appends the blocked proposal and
tool-result feedback to a copy of the provider conversation. The feedback
distinguishes withheld calls from calls already sent to the client. For an
already released call it says that execution results are unknown and the
operation must not be repeated. The caller's tool-selection constraints remain
unchanged for alternatives, including forced tool choices. A forced choice can
exhaust the alternatives instead of letting the provider return a text-only
refusal. Only the final generation changes it: when the request offers
tools, its tool choice becomes the API's no-call choice (`none`), so the model
answers in text and cannot run a provider-hosted tool such as web search. That
one generation gives up the provider's prompt cache for the messages.

During recovery, repeating a denied or previously released operation with
the same tool name and arguments is blocked even under a new call ID. This
check lasts for the current client request. It does not equate different
commands or arguments that happen to have the same effect.

After an escalation or three blocked proposals, the response ends normally
with the notices, the final generation's text (or the fixed question) and any
calls already approved and released. Before that final generation, a timeout,
malformed proposal or Watcher error ends with an error instead. The callback does not generate alternatives for missing or
failed Watcher decisions.

## The system notice

The client's next request carries the gateway's notices inside the model's
own earlier reply, as text the model did not write. Without an explanation,
models often call such text injected, or their own mistake, and retry the
denied operation. So the callback's pre-call hook adds this fixed text to
every covered request, whether or not anything has been refused:

> Watcher, your organisation's tool-call monitor, checks every tool call you
> make before it runs. When it blocks a call, the gateway removes that call
> from your reply, gives you Watcher's reason as the call's result and asks
> you to continue. So your earlier replies can contain a WATCHER NOTICE that
> you did not write: Watcher did, and the blocked call did not run. These
> notices are genuine. A block applies to that call only. Keep working on the
> user's task by another approach, including reaching the same result by
> other means: Watcher reviews every call and will block anything that is not
> allowed, so you do not need to stop and ask first. Do not repeat the
> identical blocked call. If several different approaches have been blocked,
> stop, tell the user what was blocked and ask how to proceed. A WATCHER
> ESCALATION is different from a WATCHER NOTICE: the call needs the user's
> decision before it may run. Do not try another approach and do not retry it
> unless the user allows it. End your turn by asking the user what to do, as a
> short question with labelled options, for example: A. allow this call, B.
> skip it, C. do something else. Offer to allow the call only when the
> escalation says the user can approve it.

It goes after the client's own instructions, so their cached prefix is
unchanged, and it is byte-identical on every request, so prompt caching keeps
working:

- **Messages**: a last `system` text block, without `cache_control`.
- **Chat Completions**: a `system` message after the leading system and
  developer messages.
- **Responses**: a `developer` message after the leading system and developer
  items of `input`. String input becomes that message plus a user message.

A request that already contains the text, for example because managed client
settings add it, is left unchanged, as is a request whose instruction field
has an unexpected shape. The notice is part of the request that Watcher
records and evaluates, and of every replacement generation. It is also added
in observe and paused modes, where nothing is withheld; the callback does not
know the organization's mode before the provider runs.

Every request the callback sends to Watcher sets `withholds_refused_calls`,
so Watcher records each refused call as `blocked` when it decides it.
When the client receives a response in place of refused proposals, the
callback's recording of that response names the calls it withheld in
`withheld_tool_use_ids`: each refused call and the calls withheld with it from
the same proposal. It never names a call already released to the client, nor
one the final stop-and-ask generation proposed, which Watcher never evaluates.
Watcher uses the IDs to show those calls before the delivered response. It
skips any call it never evaluated, such as one from a proposal the callback
refused as a repeat without asking Watcher.

If denial recovery ends after three refused proposals, the agent can end its
turn. For autonomous workloads that must continue, re-prompt the same
conversation with the denial message and ask the agent to use an allowed
approach. Retry at most twice per task, then stop for a person if the task is
still incomplete. Stop sooner if the agent repeats a blocked operation or
makes no progress. Resumed calls are evaluated normally.

After an escalation, stop the autonomous workload for a person to decide how
to proceed. Do not automatically resume it with an alternative approach.

## Prerequisites

- Python 3.12 or later and `uv`.
- A Watcher server from the same release as the callback and SDK or newer,
  and an API key that can monitor tool calls and write sessions.
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
export LITELLM_MASTER_KEY=...
.venv/bin/litellm --config /tmp/watcher-litellm.yaml --port 4000
```

`demo/.env.example` lists these variables and the ones the packaged
configuration reads (`LITELLM_MODEL`, `PROVIDER_API_KEY`). The callback reads
the Watcher variables when it evaluates the first response, not at import.
Use a strong generated `LITELLM_MASTER_KEY` and provision personal LiteLLM
keys for developers. Set up route restrictions before exposing the proxy.

To use a released SDK wheel in another environment, install it first, then this
package with `uv pip install --python /path/to/.venv/bin/python .`.

## Sessions and identity

Every request needs a stable identity. If `x-watcher-session-id` is supplied,
Watcher uses it as the sole session-matching ID, even for a recognized agent.
Keep it stable across turns and give each child a distinct ID to store it
separately. Reusing an ID groups those requests into one session.

Without that override, Watcher resolves native identity:

| Agent | Identity retained by Watcher |
| --- | --- |
| Claude Code | Root session UUID from metadata or `x-claude-code-session-id`; children also use `x-claude-code-agent-id`. |
| Codex | `client_metadata.thread_id`, which differs between parent and child. The family-wide `session_id` is not a conversation ID. |
| OpenCode | `x-opencode-session-id` or `x-session-id`; both must agree when present. |
| Other callers | Must supply `x-watcher-session-id`. |

The callback rejects missing or invalid selected identity with HTTP 400 before
provider generation. Custom IDs must contain 1–1,024 characters, with no control
characters, and cannot be whitespace-only. An invalid override never falls back
to native identity. A valid override ignores native identity fields, including
malformed ones, but preserves agent recognition, tool translation and grading.
Without an override, relevant native IDs must be valid and consistent; headers
belonging to other agents are ignored. Identity is not authentication; preserve
the proxy's access controls.

In API-key mode, custom IDs receive a `litellm:` prefix unless already present.
The value after that prefix must be nonempty. With an override, no native IDs are retained as
matching aliases. Identity and authentication headers are not forwarded to Watcher.

Claude Code, Codex and OpenCode supply native parent identities. Custom
integrations can pair `x-watcher-session-id` with `x-watcher-parent-session-id`;
without the latter, no new parent link is created and existing links are
preserved. See the
[parent identity contract](../../../customer-docs/docs/api/hooks.md#raw-provider-request-and-response)
for validation, account scoping and linking behavior.

The Analyzer reports LiteLLM from the capture source, independently of the
conversation ID. It retains every observed integration, including duplicate
uploads, and can filter by LiteLLM or the Gateway category.
In API-key mode, Claude and Codex native identities match local Watcher uploads.
Combining integrations can still produce extra branches or duplicate concurrent grading.

For child capture and linking limits, see
[subagent coverage](https://watcher-docs.apolloresearch.ai/concepts/subagent-coverage/#gateway-captures).

**Existing sessions:** Mixed history is not split or rewritten. Switching between
custom and native identity can start a separate session; older history remains available.

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

### Watcher behind a trusted authentication proxy

Set `WATCHER_AUTH_MODE=proxy` when Watcher accepts identity headers from a
trusted gateway. Configure these variables on the LiteLLM server:

```bash
export WATCHER_AUTH_MODE=proxy
export WATCHER_API_URL=https://watcher.example.com/api
export WATCHER_PROXY_AUTH_TOKEN=...
export WATCHER_PROXY_HEADER_USER=x-forwarded-user
export WATCHER_PROXY_HEADER_ROLE=x-forwarded-user-role
```

Use the API base URL, including `/api` unless the deployment changes that prefix.
The token must match `WATCHER_PROXY_AUTH_TOKEN` in the self-host bundle
(`XYLON_PROXY_AUTH_TOKEN` on the backend). Header names must match
Watcher's proxy-authentication settings. Keep the token in server-side secret
storage and restrict access to Watcher so callers cannot bypass its trusted
proxy. Developers do not receive this token or a Watcher API key.

Provision each LiteLLM account with a stable `user_id` and a verified
`user_email` set to the developer's company email. Watcher uses this address
to identify the developer and assign their sessions. It must match the email
their sign-in proxy sends to Watcher. The operator owns that mapping;
client headers and request-body fields do not establish identity. Shared
master keys are rejected. Accounts require an ID and valid email, except
trusted canonical `github:<numeric-id>` identities may omit email. The native
Copilot adapter verifies these IDs through GitHub. Emails must be ASCII because
they travel in HTTP headers. The callback sends the trusted identity with
the `member` role and scopes
conversation IDs to the authenticated account. Rotating its key preserves
its sessions; two accounts supplying the same conversation ID remain distinct.
Native root and child identities are resolved by the same rules as API-key
mode, then scoped to the account. Only this scoped identity is sent to Watcher,
so these sessions do not merge with a local client's native session IDs.

The stored external ID is `litellm:` followed by an account-scoped UUID,
rather than the readable aliases in the API-key example above. To derive a
generic client's stored ID for a lookup, supply the provisioned account and
the prefixed client ID to the example's helper:

```python
from litellm.proxy._types import UserAPIKeyAuth
from watcher_litellm.proxy_auth import account_session

user = UserAPIKeyAuth(user_id="developer-123", user_email="developer@example.com")
print(account_session(user, "litellm:conversation-7"))
```

Missing or blank server URL/token settings return HTTP 503 before provider
generation. Correct the gateway configuration before retrying.

## Native GitHub Copilot

The native adapter uses each developer's existing GitHub login and Copilot
seat. It does not need a personal LiteLLM key, BYOK variables, a custom
launcher or a Watcher client on the developer's machine. It is separate from
LiteLLM's dashboard account-linking flow. The example targets github.com
accounts and serves three inference formats: OpenAI Responses (GPT, Grok and
MAI), Anthropic Messages (Claude) and Chat Completions (Gemini). The Copilot
CLI reaches it through a per-user `copilotUrl` or Copilot's managed
`copilotInferenceUrl` setting. VS Code agent sessions in the Copilot harness
and the GitHub Copilot app reach it only through the managed setting (step 6).
Other Copilot clients, VS Code features outside the Copilot harness, GHE hosts,
BYOK and WebSocket inference are outside this configuration.

The gateway keeps provider-run searches out of the copy sent to Watcher, so
grouped tool-server calls also work with an older Watcher server. Native Copilot
uses the same `<server>-<tool>` name for plain and grouped calls in policy
rules, recorded calls and gateway notices, for example `desk-crm_whoami`.

The tested versions are Copilot CLI 1.0.109 and LiteLLM 1.108.3. The supplied
`copilot.yaml` uses the `github_copilot/` provider. It names tested GPT, Grok and
MAI models, and routes GPT, Claude and Gemini models through family
wildcards. Exact names win over wildcards. GitHub's model policy for each account decides which models a
developer can use; the gateway's list only decides which models it routes. Auto
selection and Copilot's built-in subagents can choose a model other than the
developer's; a request for a model the list does not route fails. When you edit
the list:

- Native GPT requests keep the Responses format, including models routed
  through `gpt-*`. Give Grok and MAI models their own entries with
  `model_info.mode: responses` so LiteLLM also keeps their Responses format.
- Keep `allowed_openai_params: [reasoning_effort]` on Gemini entries, because
  Copilot sends that field and LiteLLM otherwise refuses it.
- For a Claude model missing from LiteLLM's catalog, give it its own entry with
  `model_info.supports_adaptive_thinking: true`; otherwise LiteLLM drops the
  thinking settings Copilot sends.

1. Install this example with your chosen LiteLLM version. The dependency floor is LiteLLM 1.108.3; that is the tested version.
   Later releases need validation in your deployment. The example installs
   LiteLLM's `extra_proxy` dependencies, including the Prisma migration CLI.
   If you supply LiteLLM separately, include that extra. Copy the reference configuration:

   ```bash
   watcher-litellm-copilot-config > copilot.yaml
   ```

2. Optionally create `copilot-users.yaml` to match Copilot sessions to
   developers' browser sign-in identities. Use operator-verified, immutable
   GitHub account IDs as quoted keys and company emails as values:

   ```yaml
   "123456": developer@example.com
   ```

   Use GitHub's authenticated user API to verify the account ID. Watcher uses
   the mapped company email to identify the developer and assign their sessions.
   It must match the email their sign-in proxy sends to Watcher. Verify the
   mapping with your company directory; do not infer it from a public GitHub
   profile. Without a mapping, Watcher uses the identity
   `github:<numeric-id>`, for example `github:123456`. The file may be `{}`
   or list only some accounts. With no file configured, all accounts use
   GitHub-ID identities. A configured file must exist and contain a YAML
   mapping with valid emails; invalid files are rejected.

   The gateway verifies GitHub credentials before reading request bodies,
   including discovery and model selection. The map is not an access
   allowlist: unmapped accounts are admitted too. GitHub checks Copilot
   entitlement and model access upstream. Use network controls to restrict
   who can reach the gateway when needed. Operators control the mapping;
   client headers and request-body fields cannot choose the Watcher owner.

   An email-based browser login, including Entra, does not own sessions
   recorded under the developer's GitHub-ID identity. Reviewing those
   sessions requires cross-user permissions or an approved access request.
   Mapping changes do not reassign existing sessions. Continuing a
   conversation after a change can create a separate Watcher session under
   the new identity.

3. Configure the gateway process:

   ```bash
   export CONFIG_FILE_PATH="$PWD/copilot.yaml"
   export WATCHER_AUTH_MODE=proxy
   export WATCHER_API_URL=https://watcher.example.com/api
   export WATCHER_PROXY_AUTH_TOKEN=...
   export LITELLM_MASTER_KEY=...
   export DATABASE_URL=postgresql://litellm:password@database:5432/litellm
   ```

   If you created an email mapping file, also set:

   ```bash
   export WATCHER_COPILOT_USERS_FILE="$PWD/copilot-users.yaml"
   ```

   Leave `WATCHER_COPILOT_USERS_FILE` unset to use GitHub-ID identities for
   all accounts. Restart every gateway replica after editing the file.

   Use a strong generated master key and secret storage for credentials.
   `DATABASE_URL` names the gateway's PostgreSQL database, separate from
   Watcher's database. It must be an asyncpg-compatible PostgreSQL URL.
   The native mapping stores account-scoped session IDs, task UUIDs, spawning
   call IDs and SHA-256 task-prompt digests. It stores no GitHub credentials or
   prompt text. Keep this data across gateway restarts and provide the same
   database to every replica.

4. Run migrations separately before starting either replica. First generate
   LiteLLM's Prisma client, as the Dockerfile does; without it the gateway
   cannot start with `DATABASE_URL` set:

   ```bash
   prisma generate --schema "$(python -c 'import litellm, pathlib; print(pathlib.Path(litellm.__file__).parent / "proxy/schema.prisma")')"
   litellm --config copilot.yaml --skip_server_startup
   watcher-litellm-copilot-migrate
   export DISABLE_SCHEMA_UPDATE=true
   uvicorn watcher_litellm.copilot:app --host 0.0.0.0 --port 4000 --workers 1
   ```

   Rerun `watcher-litellm-copilot-migrate` on upgrades before starting new
   replicas. Its additive schema changes remain compatible with old replicas.
   Across the supported inference formats, a new child links to its spawning `task` call when
   its initial prompt has one exact match under that parent task. This covers
   both sync and background children. An unknown or duplicate prompt retains
   only the parent link; an assigned spawning call stays fixed across resume.
   New children keep only parent links if their parent task was handled by a
   replica without this matching support. Start new sessions after every replica has been upgraded
   to get spawning links throughout the session.

   Use two replicas with one worker each. The adapter runs around LiteLLM's
   application, so start this ASGI entry point rather than `litellm --config`.
   Keep both callback entries in `copilot.yaml`. The provider callback supplies
   native credentials; the original Watcher callback enforces tool decisions.
   Registering a subclass instead can cause LiteLLM to skip inherited hooks.

5. Expose the gateway over trusted HTTPS. Route `/copilot/` to it without
   stripping the prefix. Only discovery (`/meta`, `/models`), model selection
   (`/auto`) and HTTP inference (`/responses`, `/v1/messages` and
   `/chat/completions`) are served under that prefix. The three
   discovery/selection routes use LiteLLM's stock pass-through; inference uses
   the ordinary Copilot provider and Watcher hooks. Each inference route
   accepts only its own format's request fields and supported client tools.
   Responses also accepts grouped tools and provider-run tool searches.
   Provider-hosted actions would run before Watcher sees them and are refused.
   For the same reason, do not enable LiteLLM features that run tools inside
   the gateway, such as web search interception or MCP servers.
   Copilot's deferred MCP tools (grouped by server in a `namespace` tool) and
   its `tool_search` are accepted on Responses: GitHub's search only loads
   definitions the request already lists, and any tool the model then calls is
   held for Watcher. A refused request logs `copilot_request_refused` with the
   reason and number of rejected fields, headers or tool types. Names and
   values stay out of logs. Other
   inference routes and WebSockets are rejected. Keep request/response body
   logging disabled on the ingress and gateway. The supplied configuration
   disables LiteLLM message and spend logging.

6. Each developer signs in to the normal Copilot CLI and sets `copilotUrl` in
   `~/.copilot/settings.json` (or `$COPILOT_HOME/settings.json` when overriding
   the configuration directory) to the gateway's HTTPS URL ending in `/copilot`.
   Preserve their other settings. Their existing GitHub credential travels to the
   gateway and GitHub; developers do not receive the Watcher proxy token.
   This per-user setting applies only to the CLI, and developers can remove it.
   To route the Copilot CLI, VS Code agent sessions in the Copilot harness and
   the GitHub Copilot app through the gateway on managed devices, deploy
   Copilot's managed setting instead, for example in
   `/Library/Application Support/GitHubCopilot/managed-settings.json` on macOS:

   ```json
   {"copilotInferenceUrl": "https://copilot.example.com/copilot"}
   ```

   Each client must be at least: Copilot CLI 1.0.106, VS Code 1.146.0, GitHub
   Copilot app 1.2.0. Older clients ignore the setting and call GitHub
   directly. Sign-in and model discovery stay with GitHub.
   [Native Copilot through LiteLLM](https://watcher-docs.apolloresearch.ai/self-hosting/native-copilot-gateway)
   covers the file location on each OS, permissions and verification.

Native `x-client-session-id` identifies the root conversation across resume.
Task and parent headers identify child conversations. The adapter stores the
mapping before inference and sends both identities, plus any matched spawning
call ID, with every captured child exchange. Watcher records these links through
the shared capture path. A failed link does not fail the response; later child
captures retry it, including unresolved spawning-message links. Without another
capture a failed link can remain missing. Unknown parents, conflicting ancestry
and unavailable task storage still stop the request. Deleting the mapping table
breaks resumes and must be coordinated with retiring the corresponding sessions.

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
  The final stop-and-ask generation is the exception: its failure ends the
  response with a fixed question to the user instead.
- An unsupported or malformed provider response, including a complete reply
  the callback cannot combine during recovery: HTTP 422 before streaming starts.
- Once any stream has started, failures arrive as an error event in that API's
  streaming protocol. The pending call and unreleased content are withheld;
  previously released text and approved calls remain delivered. Policy denials
  and escalations instead use the bounded recovery flow above.

Before any denial, each tool evaluation has a **300-second wall-clock
deadline**. It starts when evaluation begins; earlier provider generation does
not consume it. A non-streaming proposal has one deadline for its whole
evaluation.

The first denial or escalation changes the scope: the rest of recovery shares
that refused evaluation's existing deadline. Draining its provider stream,
generating both possible alternatives, evaluating their calls and the final
text-only generation all consume the remaining time. An evaluation that takes 120 seconds leaves at most
180 seconds for recovery. Alternatives do not get a fresh 300 seconds.
Expiry before the final generation reports a timeout and withholds pending
calls. Expiry or a provider failure during the final generation is not an
error: the response ends with the fixed question instead, so a client does not
retry and regenerate the refused proposals. Keepalives do not extend either
deadline.

This is separate from Watcher's own per-stage timeouts. The callback overrides
the SDK's 420-second raw-hook default and applies a total deadline in addition
to its HTTP timeout. Watcher may finish and record grading, including its
usage, after the callback times out or the client disconnects.

The callback does not retry a Watcher request that failed or timed out, because
a retry can repeat billed LLM grading.

## Limits

- Routes other than the three above, including Realtime, WebSockets, batches,
  files and LiteLLM's provider pass-through endpoints (such as `/gemini` or
  `/bedrock`), are not checked. Block them in an enforcing deployment.
- Tools that run on the provider's servers (for example hosted web search)
  execute before the response exists and cannot be prevented. Provider-run
  tool searches pass through as context; the client call they select is
  evaluated before release.
- Calls created by the client itself cannot be judged before execution by a
  model gateway. Copilot's `read_agent` after a background child finishes or
  fails is one example; it can appear in later history as not evaluated.
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
alternatives after denial, the final question after escalation, retry limits,
timeouts, disconnects and the withheld calls named when the delivered response
is recorded.
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
