"""Resolve native or custom conversation identity at a gateway boundary.

Adapters validate the original request before generation and send the resulting
identities to Watcher. Headers stay at the gateway. Selection
reads no transcript history, performs no I/O and grants no access.
"""

import json
import re
from collections.abc import Mapping
from uuid import UUID

from pydantic import BaseModel

from watcher_sdk.capture import ConversationIdentity, validate_conversation_id

IDENTITY_HEADER_NAMES = frozenset(
    {
        "x-watcher-session-id",
        "x-watcher-parent-session-id",
        "x-claude-code-session-id",
        "x-claude-code-agent-id",
        "x-claude-code-parent-agent-id",
        "x-opencode-session-id",
        "x-opencode-parent-session-id",
        "x-session-id",
        "x-parent-session-id",
    }
)
_CLAUDE_HEADERS = frozenset({"x-claude-code-session-id", "x-claude-code-agent-id"})
_OPENCODE_HEADERS = frozenset({"x-opencode-session-id", "x-session-id"})
_OPENCODE_USER_AGENT = re.compile(r"^opencode(?:[/\s]|$)")
_CODEX_USER_AGENT = re.compile(r"^codex(?:[_/\s-]|$)", re.IGNORECASE)
_CLAUDE_METADATA = re.compile(r"user_\w+_account_[\w-]+_session_(.+)")


class GatewayConversation(BaseModel):
    """Selected identity and optional immediate parent.

    The parent is evidence supplied by the caller, not an authorization grant.
    Adapters must apply the same identity transformation to both fields.
    """

    conversation: ConversationIdentity
    parent_conversation: ConversationIdentity | None = None


def resolve_gateway_conversation(
    request_body: Mapping[str, object], request_headers: Mapping[str, object], user_agent: str | None
) -> GatewayConversation:
    """Validate the selected conversation and its explicitly identified immediate parent.

    ``resolve_conversation_identity`` defines custom precedence and native
    identity requirements; this function adds parent validation.
    Custom overrides accept only ``x-watcher-parent-session-id`` as parent
    evidence. Codex supplies a parent-thread ID; Claude supplies the root plus
    an optional parent-agent ID for nested children. OpenCode supplies parent
    session headers. Missing evidence leaves the conversation unlinked;
    malformed relevant evidence or self-parentage raises ValueError
    before generation. Headers for other harnesses remain irrelevant.
    """
    conversation = resolve_conversation_identity(request_body, request_headers, user_agent)
    custom_parent = _selected_headers(request_headers, frozenset({"x-watcher-parent-session-id"}))
    parent = None
    if custom_parent:
        if conversation.namespace != "other":
            raise ValueError("custom_parent_requires_custom_conversation")
        parent = ConversationIdentity(namespace="other", id=custom_parent["x-watcher-parent-session-id"])
    elif conversation.namespace == "codex":
        metadata = request_body.get("client_metadata")
        if isinstance(metadata, dict) and "x-codex-parent-thread-id" in metadata:
            parent = ConversationIdentity(namespace="codex", id=_uuid(metadata["x-codex-parent-thread-id"]))
    elif conversation.namespace == "claude_code":
        headers = _selected_headers(request_headers, frozenset({"x-claude-code-parent-agent-id"}))
        if conversation.id.startswith("subagent:"):
            root, _agent = json.loads(conversation.id.removeprefix("subagent:"))
            parent_agent = headers.get("x-claude-code-parent-agent-id")
            parent = ConversationIdentity(
                namespace="claude_code",
                id="subagent:" + json.dumps([root, parent_agent]) if parent_agent is not None else root,
            )
        elif headers:
            raise ValueError("claude_parent_requires_child_identity")
    elif conversation.namespace == "opencode":
        headers = _selected_headers(request_headers, frozenset({"x-opencode-parent-session-id", "x-parent-session-id"}))
        parent_id = headers.get("x-opencode-parent-session-id")
        alias = headers.get("x-parent-session-id")
        if parent_id is not None and alias is not None and parent_id != alias:
            raise ValueError("conflicting_opencode_parent_identity")
        parent_id = parent_id or alias
        if parent_id is not None:
            parent = ConversationIdentity(namespace="opencode", id=parent_id)
    if parent == conversation:
        raise ValueError("conversation_cannot_parent_itself")
    return GatewayConversation(conversation=conversation, parent_conversation=parent)


def claude_metadata_session(request_body: Mapping[str, object]) -> str | None:
    """Read legacy or JSON Claude session metadata without validating its ID.

    Unrelated or malformed provider metadata returns None. Native gateway identity
    validates the returned UUID separately; legacy capture callers retain their
    existing acceptance of nonempty string session IDs.
    """
    metadata = request_body.get("metadata")
    user_id = metadata.get("user_id") if isinstance(metadata, dict) else None
    if not isinstance(user_id, str):
        return None
    match = _CLAUDE_METADATA.match(user_id)
    if match:
        return match.group(1)
    try:
        identity = json.loads(user_id)
    except ValueError:
        return None
    session_id = identity.get("session_id") if isinstance(identity, dict) else None
    return session_id if isinstance(session_id, str) and session_id.strip() else None


def _selected_headers(headers: Mapping[str, object], names: frozenset[str]) -> dict[str, str]:
    """Validate only selected identity headers, including conflicting case variants."""
    selected: dict[str, str] = {}
    for name, value in headers.items():
        key = name.lower()
        if key in names:
            validated = validate_conversation_id(value, max_length=1024)
            if key in selected and selected[key] != validated:
                raise ValueError("conflicting_identity_headers")
            selected[key] = validated
    return selected


def _uuid(value: object) -> str:
    """Normalize a native session UUID, returning a content-free validation error."""
    try:
        return str(UUID(validate_conversation_id(value, max_length=1024)))
    except ValueError:
        raise ValueError("invalid_native_conversation_identity") from None


def resolve_conversation_identity(
    request_body: Mapping[str, object], request_headers: Mapping[str, object], user_agent: str | None
) -> ConversationIdentity:
    """Select one custom override or native conversation from the original request.

    Pass only allowlisted identity headers. Unsupported names always fail;
    irrelevant allowed headers are discarded before value validation. A custom
    header takes precedence even when native evidence is malformed. Without
    one, Claude uses its root UUID and optional child ID, Codex its thread UUID,
    and OpenCode its agreeing session headers. Other applications need a custom
    ID. Errors use fixed messages safe to return before provider generation.

    The custom header is ``x-watcher-session-id``. Filter original headers to
    ``IDENTITY_HEADER_NAMES`` before calling; never forward authentication.
    Claude uses ``metadata.user_id`` (JSON session_id or legacy session suffix),
    ``x-claude-code-session-id`` and optional ``x-claude-code-agent-id``.
    Codex uses ``client_metadata.thread_id``; OpenCode uses
    ``x-opencode-session-id`` and ``x-session-id``. Native selection recognizes
    claude-cli/, codex and opencode user-agent families. Invalid selected input
    raises ValueError; catch it to reject before provider generation.

    User-agent markers select the relevant native fields. Without a marker,
    Claude or Codex body metadata can identify the conversation; a generic
    ``x-session-id`` cannot establish an OpenCode conversation by itself.
    """
    if any(name.lower() not in IDENTITY_HEADER_NAMES for name in request_headers):
        raise ValueError("unsupported_identity_header")
    custom = _selected_headers(request_headers, frozenset({"x-watcher-session-id"}))
    if custom:
        return ConversationIdentity(namespace="other", id=custom["x-watcher-session-id"])

    user_agent = user_agent or ""
    root = claude_metadata_session(request_body)
    metadata = request_body.get("client_metadata")
    thread = metadata.get("thread_id") if isinstance(metadata, dict) else None
    if _OPENCODE_USER_AGENT.match(user_agent):
        headers = _selected_headers(request_headers, _OPENCODE_HEADERS)
        session_id = headers.get("x-opencode-session-id")
        alias = headers.get("x-session-id")
        if session_id is not None and alias is not None and session_id != alias:
            raise ValueError("conflicting_opencode_session_identity")
        native_id = session_id or alias
        if native_id is None:
            raise ValueError("missing_native_conversation_identity")
        return ConversationIdentity(namespace="opencode", id=native_id)
    if _CODEX_USER_AGENT.match(user_agent) or (thread is not None and not user_agent.startswith("claude-cli/")):
        native_id = _uuid(thread)
        return ConversationIdentity(namespace="codex", id=native_id)
    if user_agent.startswith("claude-cli/") or root is not None:
        headers = _selected_headers(request_headers, _CLAUDE_HEADERS)
        claude_metadata = request_body.get("metadata")
        if root is None and isinstance(claude_metadata, dict) and "user_id" in claude_metadata:
            raise ValueError("invalid_native_conversation_identity")
        header_root = headers.get("x-claude-code-session-id")
        root = _uuid(root) if root is not None else None
        header_root = _uuid(header_root) if header_root is not None else None
        if root is not None and header_root is not None and root != header_root:
            raise ValueError("conflicting_claude_session_identity")
        root = header_root or root
        if root is None:
            raise ValueError("missing_claude_root_identity")
        agent_id = headers.get("x-claude-code-agent-id")
        native_id = "subagent:" + json.dumps([root, agent_id], separators=(",", ":")) if agent_id is not None else root
        return ConversationIdentity(namespace="claude_code", id=native_id)
    raise ValueError("missing_gateway_conversation_identity")
