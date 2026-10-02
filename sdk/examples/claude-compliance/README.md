# Claude Compliance API

Import a retained Claude Enterprise conversation into Watcher. The example reads
Claude chat, local-session or remote-session transcripts and records their text,
tool calls and tool results through the public Watcher SDK.

This is a retrospective import. Claude's Compliance API is a read-only source;
it does not accept Watcher exports. The example does not block actions or request
tool judgments. It is an example you can adapt, not an officially supported connector.

## Requirements

You need Python 3.12 or later, [uv](https://docs.astral.sh/uv/), a Watcher API key
with session-write permission, and a Claude Enterprise **Compliance Access Key**
with `read:compliance_user_data`. An Anthropic inference key, analytics key or
Console Admin API key cannot retrieve these transcripts. See Anthropic's
[access guide](https://platform.claude.com/docs/en/manage-claude/compliance-api-access).

Choose a conversation ID from the corresponding Compliance API endpoint:

| `CLAUDE_COMPLIANCE_FAMILY` | Source | ID comes from |
| --- | --- | --- |
| `chats` | Claude Enterprise chats | `GET /v1/compliance/apps/chats` |
| `local` | Captured sessions on users' machines, including Claude Code and Cowork | `GET /v1/compliance/apps/sessions/local` |
| `remote` | Cowork sessions hosted by Anthropic | `GET /v1/compliance/apps/sessions/remote` |

The example imports one explicitly selected conversation per invocation. It does
not continuously discover or synchronize an organization's conversations.

## Install and run

From this directory in the SDK source checkout:

```sh
uv sync
export WATCHER_URL='https://your-watcher-server/api'
export WATCHER_API_KEY='your-watcher-api-key'
export ANTHROPIC_COMPLIANCE_ACCESS_KEY='your-compliance-access-key'
export CLAUDE_COMPLIANCE_FAMILY='local'
export CLAUDE_COMPLIANCE_ID='your-compliance-session-id'
uv run python demo/import_session.py
```

Supply real credentials through your usual secret-management mechanism. The
command reads the selected transcript from Anthropic and sends it to the Watcher
server you configured. Confirm that this destination and its retention policy
are appropriate for your organization's transcript data.

The command reports the number of submitted messages and capture limitations.
`import-receipt.json` contains `status: "submitted"`, the stable external ID,
source digest, submission time and limitations. Set `COMPLIANCE_RECEIPT` to choose another file. Give each
concurrent importer its own receipt path.

In Watcher, find the external ID recorded in the receipt and inspect the transcript.
Text, tool IDs, tool results and the final answer should match the returned source
content. An imported conversation has no new tool judgments from this example.

## Use in your application

```python
import httpx
from watcher_sdk import AsyncWatcherClient
from watcher_claude_compliance import ComplianceClient, import_conversation

async with httpx.AsyncClient(
    base_url="https://api.anthropic.com",
    headers={"x-api-key": compliance_key, "anthropic-version": "2023-06-01"},
    timeout=30,
) as source_http, AsyncWatcherClient(watcher_url, api_key=watcher_key) as watcher:
    receipt = await import_conversation(
        ComplianceClient(source_http),
        watcher,
        family="local",
        conversation_id=session_id,
    )
```

`ComplianceClient` fetches every transcript page before calling Watcher. It uses
the source's documented cursor for each endpoint family and preserves returned
message order. The page limit defaults to 1,000 pages; use
`ComplianceClient(source_http, max_pages=...)` for larger imports. HTTP reads
have bounded retries, including transient overload responses, and honor
Anthropic's `x-should-retry: false` instruction. An expired cursor, changed
message or repeated cursor stops the import; rerun it to start a fresh page walk.

The hook returns before persistence completes. A receipt confirms submission,
not stored content; inspect the actual conversation in Watcher before relying on
the import. Source and HTTP errors leave the previous local receipt unchanged,
but a timeout does not prove that Watcher stored nothing. A later storage failure
does not update an already written receipt.

Receipts do not cause subsequent runs to skip delivery: source history and
destination state can change. Replays reuse the same external conversation
identity; this is not an exactly-once guarantee. Compare the stored transcript
with the source if a replay contains changed tool identities or shortened history.

## Coverage and limitations

| Area | Behavior |
| --- | --- |
| Text and tools | Preserves text, complete JSON arguments, source tool IDs, results and tool errors. Boolean and numeric argument values remain distinct. |
| Missing or truncated data | Rejects deleted chats before importing. Represents contentless messages explicitly and records a limitation. Retains unavailable-content markers, text/result truncation flags and source provenance. Rejects truncated tool arguments, absent tool IDs, ambiguous tool pairings and unknown content blocks. |
| Historical time | Retains each source timestamp in message metadata. Watcher's generic ingestion path dates messages at import time, so Watcher time filters do not represent the original conversation time. |
| Files and reasoning | Does not download attachments or artifacts. Anthropic omits thinking blocks and some other content; the example cannot recover it. |
| Account coverage | Local capture requires an eligible Enterprise-authenticated session and enabled Compliance API. Anthropic excludes several session types and retention configurations. Remote sessions here are Cowork sessions, not Claude Code cloud sessions. |
| Identity | Uses the source family, organization and conversation ID. It does not assume a Compliance session ID matches the native Claude Code ID, and does not impersonate a Watcher user. |
| Retention | Source deletion or retention expiry does not delete an imported Watcher copy. A later import can contain changed or shortened history; inspect the stored conversation after replay. |
| Monitoring | Records conversation history only. No synchronous prevention, retroactive blocking or automatic tool grading. |

See Anthropic's [session coverage](https://platform.claude.com/docs/en/manage-claude/compliance-sessions)
and [chat content reference](https://platform.claude.com/docs/en/api/compliance/apps/chats/messages/list)
for the source's availability and capture limits.

## Tests

```sh
uv run pytest
```

Tests use synthetic documented responses, a real loopback HTTP source and the
public Watcher SDK against a local receiver. They check pagination, conversion,
source limitations, retries and receipt behavior. They do not establish Enterprise
account access or persistence in a deployed Watcher server. `metadata.yaml`
records the verification level and dependency information.

The Compliance API has no installed provider package to version. Its deployed
version remains unknown in metadata for fixture tests; the `anthropic-version`
request header identifies an API schema, not an observed server release.

For the complete installed-package check in a container with networking disabled,
run `bash tests/native/run.sh`. It requires Docker and uv. Dependency installation
runs before the isolated tests; the script prints the directory containing its
test results. It builds the adjacent SDK unless `WATCHER_SDK_WHEEL` supplies a
wheel, and compares installed SDK files with that wheel before testing.

`src/watcher_claude_compliance/` contains the installable adapter;
`demo/import_session.py` is the runnable entry point; `tests/` contains fixtures
and behavioral tests. The package manifest uses the adjacent SDK checkout for
local development.
