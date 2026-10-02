"""Validate Copilot event logs and convert supported conversations for the public SDK."""

import asyncio
import base64
import binascii
import hashlib
import math
import re
import time
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    TypeAdapter,
    ValidationError,
    field_validator,
    model_validator,
)

from watcher_github_copilot_cli.configuration import copilot_home

MAX_TRANSCRIPT_BYTES = 256 * 1024 * 1024
MAX_HOOK_EVENT_BYTES = 16 * 1024 * 1024
# Every turn resends the whole history within Watcher's default 8 MiB request limit,
# and Copilot's view tool returns whole files, so one large result would otherwise
# stop recording the session for good. The cut is deterministic, so later snapshots
# still extend earlier ones.
MAX_TOOL_TEXT = 128 * 1024
# The text Copilot gives the model for a call that never returned.
INTERRUPTED = "The execution of this tool, or a previous tool was interrupted."
# Watcher's own compaction marker: the Analyzer draws a "Context compacted" card
# for a system message carrying this metadata, and its monitors were calibrated
# on this exact notice text. Keep both byte-identical to Watcher's.
COMPACTION_NOTICE = "[COMPACTION NOTICE]\nThe agent's earlier context was compacted at this point.\n[END NOTICE]"
# Marks where events were left out because they could not be read: a line that is
# not an event, an event with malformed fields, or a tool call or result that
# repeats or contradicts an earlier one. Copilot writes whole, consistent events,
# but the agent can append to its log and a crash can leave a broken line; refusing
# the whole log would stop recording the rest of the session for good.
SKIPPED_EVENT_NOTICE = (
    "[SKIPPED EVENT NOTICE]\nCopilot's log has one or more events here that this integration could not read, "
    "so they are left out.\n[END NOTICE]"
)
_SKIPPED_METADATA: dict[str, JsonValue] = {"github_copilot_cli": {"skipped_events": True}}
# read_events puts an event of this type where a line was not a readable event.
UNREADABLE_EVENT = "github_copilot_cli.unreadable_event"
JSON_OBJECT = TypeAdapter(dict[str, JsonValue], config=ConfigDict(allow_inf_nan=False))
_MESSAGE = TypeAdapter(dict[str, JsonValue])

# Watcher's built-in command rules and per-tool thresholds name Claude Code's tools
# (Bash, Read, Write, Edit and so on). Watcher translates the tools of harnesses it
# can identify onto those names, but a public SDK caller cannot say it is Copilot, so
# this sample translates Copilot's tools itself: a tool that does what the Claude Code
# tool does gets its name, and a file tool's ``path`` becomes ``file_path``. The gate
# and the recorded history use the same translation, so the gate can name the
# recorded call it judged and Watcher stores its decision on that call.
_POLICY_NAMES: dict[str, tuple[str, str | None]] = {
    "bash": ("Bash", None),
    # Copilot lists local_shell beside bash as a native shell and displays it the
    # same way, so it gets Bash too, or a command could miss Bash rules under this name.
    "local_shell": ("Bash", None),
    # The Windows shell gets Claude Code's own PowerShell tool rather than Bash:
    # Watcher's Bash allow rules assume POSIX shell syntax and never allow PowerShell.
    "powershell": ("PowerShell", None),
    "view": ("Read", "path"),
    "create": ("Write", "path"),
    "edit": ("Edit", "path"),
    "glob": ("Glob", None),
    "grep": ("Grep", None),
    "web_fetch": ("WebFetch", None),
    "web_search": ("WebSearch", None),
    "rg": ("Grep", None),
    "task": ("Agent", None),
    "skill": ("Skill", None),
}

# Tools that type text into a running shell, and the shell tool that text is judged as.
_TYPED_SHELLS = {"write_bash": "Bash", "write_powershell": "PowerShell"}

# ``str_replace_editor`` reads, creates or edits a file depending on its
# ``command``, so each command gets the Claude Code tool that does the same thing.
# Any other command keeps the native name, so rules written for these tools never
# judge something they do not do.
_EDITOR_COMMANDS = {"view": "Read", "create": "Write", "str_replace": "Edit", "insert": "Edit"}

# The operations of Copilot's ``lsp`` tool that only read. Its ``rename`` edits
# files across the project, while Claude Code's LSP only reads and passes without
# grading by default, so ``rename`` and any operation not listed keep the native name.
_LSP_READS = frozenset(
    {
        "goToDefinition",
        "findReferences",
        "hover",
        "documentSymbol",
        "workspaceSymbol",
        "goToImplementation",
        "incomingCalls",
        "outgoingCalls",
    }
)


# Headers of the patch format GPT models send through ``apply_patch``. Each names
# one path the patch creates, changes, removes or moves something to. Matched
# against a line with its surrounding whitespace removed (see ``patch_paths``).
_PATCH_HEADER = re.compile(r"\*\*\*[ \t]*(Add File|Update File|Delete File|Move to):[ \t]*(.*)")
PATCH_START = "*** Begin Patch"
# Copilot's patch parser starts a line at LF, CR or CRLF, and trims the characters
# JavaScript's String.prototype.trim removes, listed below, from each line and each
# path. That set includes the byte order mark U+FEFF, unlike Python's str.strip(),
# and leaves out U+0085 and U+001C to U+001F, which str.strip() also removes.
_PATCH_LINE_BREAK = re.compile(r"\r\n|\r|\n")
_PATCH_TRIM = (
    "\t\n\x0b\x0c\r \xa0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a"
    "\u2028\u2029\u202f\u205f\u3000\ufeff"
)


def patch_paths(patch: str) -> list[tuple[str, str]]:
    """The ``(header, path)`` pairs an ``apply_patch`` patch names, in order, without duplicates.

    Copilot's own patch parser splits lines at LF, CR and CRLF, trims each line
    before it looks for a header, and trims the path after it (see
    ``_PATCH_TRIM``), so an indented, byte-order-mark-led or CR-separated header
    still names a file that Copilot writes. This reads every line the same way.
    It also accepts headers Copilot rejects, such as one without a space after
    the colon, and a header-like context line inside a hunk: judging an extra
    path is safe, while missing one would let a call escape the rules for it. An
    empty list means the text names no path this adapter can read.
    """
    found: list[tuple[str, str]] = []
    for line in _PATCH_LINE_BREAK.split(patch):
        match = _PATCH_HEADER.fullmatch(line.strip(_PATCH_TRIM))
        if match is None:
            continue
        header, path = match.group(1), match.group(2).strip(_PATCH_TRIM)
        if path and (header, path) not in found:
            found.append((header, path))
    return found


def patch_tool(header: str) -> str:
    """The Claude Code tool one patch path is judged as.

    ``Write`` for a file the patch creates, an added file or a ``Move to`` target,
    and ``Edit`` for a file it changes or deletes.
    """
    return "Write" if header in {"Add File", "Move to"} else "Edit"


def policy_call(name: str, arguments: dict[str, JsonValue]) -> tuple[str, dict[str, JsonValue]]:
    """Copilot's tool call under the Claude Code name and arguments Watcher's policy uses.

    Watcher's rules and thresholds name Claude Code's tools, and the server cannot
    tell that an SDK request comes from Copilot, so both the gate and the recorded
    history use these names. See ``_POLICY_NAMES`` for the direct renames.

    ``write_bash`` and ``write_powershell`` type into a running shell; they become
    ``Bash`` and ``PowerShell`` with the typed text as ``command``, so shell rules
    see it, keeping their other fields. ``str_replace_editor`` is named after its
    ``command`` (see ``_EDITOR_COMMANDS``), with ``path`` as ``file_path``. ``lsp``
    becomes ``LSP`` only for an operation that reads (see ``_LSP_READS``), with
    ``file`` as ``filePath``, Claude Code's key for it. GPT's
    freeform ``apply_patch`` is named after its first path's operation, ``Write``
    when it adds that file and ``Edit`` otherwise (see ``patch_tool``), with the
    first path as ``file_path``. A patch naming several paths also lists them all
    under ``file_paths``; the raw patch stays under ``input``. Edit and Write rules
    match ``file_path`` only, so the gate checks each further path separately,
    under its own operation's tool. Text that starts a patch (``PATCH_START``) but
    names no path ``patch_paths`` can read becomes ``Edit`` with its arguments
    unchanged, so it never falls outside every Edit and Write rule and threshold
    under the native name. Other text, non-text typed input, an editor command or
    ``lsp`` operation not listed, and MCP or other unmapped tools keep their names
    and arguments. A mapped file tool whose path is not text keeps its arguments
    under the Claude Code name.

    The keys this function derives always win over keys of the same name the model
    supplied. Rules read ``command`` and ``file_path``, so a model that added its
    own ``command`` to ``write_bash``, or a ``file_path`` to ``apply_patch``, could
    otherwise have a harmless value judged in place of what actually runs.
    """
    typed_shell = _TYPED_SHELLS.get(name)
    if typed_shell is not None:
        typed = arguments.get("input")
        if not isinstance(typed, str):
            return name, arguments
        return typed_shell, {"command": typed} | {
            key: value for key, value in arguments.items() if key not in {"input", "command"}
        }
    if name == "str_replace_editor":
        command = arguments.get("command")
        editor_tool = _EDITOR_COMMANDS.get(command) if isinstance(command, str) else None
        if editor_tool is None:
            return name, arguments
        return editor_tool, _renamed_path(arguments, "path", "file_path")
    if name == "lsp":
        operation = arguments.get("operation")
        if not isinstance(operation, str) or operation not in _LSP_READS:
            return name, arguments
        return "LSP", _renamed_path(arguments, "file", "filePath")
    if name == "apply_patch":
        patch = arguments.get("input")
        if not isinstance(patch, str):
            return name, arguments
        paths = patch_paths(patch)
        if not paths:
            return ("Edit", arguments) if PATCH_START in patch else (name, arguments)
        canonical = patch_tool(paths[0][0])
        translated: dict[str, JsonValue] = {"file_path": paths[0][1]}
        if len(paths) > 1:
            translated["file_paths"] = [path for _, path in paths]
        return canonical, translated | {
            key: value for key, value in arguments.items() if key not in {"file_path", "file_paths"}
        }
    canonical, path_key = _POLICY_NAMES.get(name, (name, None))
    if path_key is not None:
        arguments = _renamed_path(arguments, path_key, "file_path")
    return canonical, arguments


def _renamed_path(arguments: dict[str, JsonValue], native: str, canonical: str) -> dict[str, JsonValue]:
    """``arguments`` with the path under ``native`` moved to ``canonical``, replacing any value already there.

    A path that is missing or not text leaves ``arguments`` unchanged.
    """
    path = arguments.get(native)
    if not isinstance(path, str):
        return arguments
    return {key: value for key, value in arguments.items() if key != native} | {canonical: path}


class TranscriptError(ValueError):
    """A transcript failure whose fixed message is safe to show without native content."""


class UnsupportedTranscriptError(TranscriptError):
    pass


class IncompleteTranscriptError(TranscriptError):
    pass


def check_deadline(deadline: float | None) -> None:
    if deadline is not None and time.monotonic() >= deadline:
        raise TimeoutError("Processing the Copilot log used the whole deadline")


class NativeModel(BaseModel):
    model_config = ConfigDict(strict=True, extra="ignore", allow_inf_nan=False)


class CompletedTurn(NativeModel):
    sessionId: Annotated[UUID, Field(strict=False)]
    transcriptPath: str
    stopReason: Literal["end_turn"] | None = None
    timestamp: int | None = None


class SessionEnded(NativeModel):
    sessionId: Annotated[UUID, Field(strict=False)]
    reason: str
    timestamp: int | None = None


class EventKind(NativeModel):
    """The routing fields every event carries; ``agentId`` marks a subagent's own events."""

    type: str
    agentId: Annotated[str, Field(min_length=1)] | None = None


class MessageData(NativeModel):
    parentToolCallId: str | None = None


class WithoutAttachments(MessageData):
    attachments: None = None

    @field_validator("attachments", mode="before")
    @classmethod
    def reject_attachments(cls, value: JsonValue) -> None:
        if value is not None and value != []:
            raise UnsupportedTranscriptError("Attachments are only supported on user messages")


class UserData(MessageData):
    content: str
    transformedContent: str = ""
    attachments: list[dict[str, JsonValue]] | None = None


class SystemContentBlock(NativeModel):
    content: str


class SystemData(WithoutAttachments):
    role: Literal["system"]
    content: str
    contentBlocks: list[SystemContentBlock] | None = None


class ToolRequest(NativeModel):
    toolCallId: Annotated[str, Field(min_length=1)]
    name: Annotated[str, Field(min_length=1)]
    arguments: dict[str, JsonValue] = Field(default_factory=dict)
    type: Literal["function"] = "function"


class CustomToolRequest(NativeModel):
    """A freeform tool such as ``apply_patch``, whose input is raw text rather than JSON."""

    toolCallId: Annotated[str, Field(min_length=1)]
    name: Annotated[str, Field(min_length=1)]
    arguments: str
    type: Literal["custom"]


class EmptyServerTools(NativeModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    provider: Annotated[str, Field(min_length=1)]


class ReasoningBlocks(NativeModel):
    provider: Annotated[str, Field(min_length=1)]
    blocks: list[JsonValue] = Field(default_factory=list)

    def has_readable_text(self) -> bool:
        """Detect Anthropic ``thinking`` or OpenAI ``summary``/``content`` text in the raw blocks."""
        for block in self.blocks:
            if not isinstance(block, dict):
                continue
            thinking = block.get("thinking")
            if isinstance(thinking, str) and thinking.strip():
                return True
            for key in ("summary", "content"):
                parts = block.get(key)
                if isinstance(parts, list) and any(
                    isinstance(part, dict) and isinstance(part.get("text"), str) and str(part["text"]).strip()
                    for part in parts
                ):
                    return True
        return False


class AssistantData(WithoutAttachments):
    content: str
    toolRequests: list[ToolRequest | CustomToolRequest] = Field(default_factory=list)
    serverTools: EmptyServerTools | None = None
    reasoningText: str | None = None
    reasoningOpaque: str | None = None
    encryptedContent: str | None = None
    reasoningBlocks: ReasoningBlocks | None = None
    providerContentBlocks: None = None
    chunkIndex: int | None = None
    chunkCount: int | None = None

    @field_validator("serverTools", mode="before")
    @classmethod
    def reject_hosted_tools(cls, value: JsonValue) -> EmptyServerTools | None:
        if value is None or value == [] or value == {}:
            return None
        try:
            return EmptyServerTools.model_validate(value)
        except ValidationError:
            raise UnsupportedTranscriptError("Provider-hosted tools are unsupported") from None

    @field_validator("providerContentBlocks", mode="before")
    @classmethod
    def reject_unrepresented_content(cls, value: JsonValue) -> None:
        if value is not None and value != "" and value != [] and value != {}:
            raise UnsupportedTranscriptError("Provider content blocks are unsupported")

    @model_validator(mode="after")
    def reject_reasoning_missing_from_text(self) -> Self:
        if self.reasoningBlocks and self.reasoningBlocks.has_readable_text() and not (self.reasoningText or "").strip():
            raise UnsupportedTranscriptError("Readable reasoning is only in provider blocks")
        return self


class ToolResult(NativeModel):
    content: str
    binaryResultsForLlm: list[dict[str, JsonValue]] | None = None
    citableSources: list[JsonValue] | None = None


class ToolError(NativeModel):
    message: str


class ToolCompleteData(WithoutAttachments):
    toolCallId: Annotated[str, Field(min_length=1)]
    success: bool
    result: ToolResult | None = None
    error: ToolError | None = None


class UserCommand(NativeModel):
    command: str


class UserToolRequestData(NativeModel):
    toolCallId: Annotated[str, Field(min_length=1)]
    arguments: UserCommand


class SessionStartData(NativeModel):
    sessionId: Annotated[UUID, Field(strict=False)]


class CompactionData(NativeModel):
    success: bool
    summaryContent: str | None = None
    checkpointNumber: int | None = None


class TruncationData(NativeModel):
    messagesRemovedDuringTruncation: Annotated[int, Field(ge=0)]


class ResumeData(NativeModel):
    alreadyInUse: bool = False
    sessionWasActive: bool = False
    continuePendingWork: bool = False


class SessionErrorData(NativeModel):
    errorType: str
    statusCode: int | None = None


class NoticeData(NativeModel):
    """Text Copilot injected into the model's context outside a user's own message."""

    content: str


class NotificationKind(NativeModel):
    type: str


class NotificationData(NoticeData):
    kind: NotificationKind


class SkillReferenceData(NativeModel):
    contentId: Annotated[str, Field(min_length=1)]
    prefix: str
    suffix: str


class HandoffData(NativeModel):
    summary: str | None = None
    context: JsonValue = None
    sourceType: str | None = None
    remoteSessionId: str | None = None


class SubagentData(NativeModel):
    toolCallId: Annotated[str, Field(min_length=1)]


class TurnBoundaryData(NativeModel):
    turnId: str


class TurnBoundaryEvent(NativeModel):
    type: Literal["assistant.turn_start", "assistant.turn_end"]
    data: TurnBoundaryData


class HookKindData(NativeModel):
    hookType: str


class HookKindEvent(NativeModel):
    type: Literal["hook.start"]
    data: HookKindData


class AgentStopData(NativeModel):
    hookType: Literal["agentStop"]
    input: CompletedTurn


class AgentStopEvent(NativeModel):
    type: Literal["hook.start"]
    data: AgentStopData


# The data model of each event type this sample records. Other types are either in
# _IGNORED_EVENTS or recorded as an unsupported-event notice.
_DATA: dict[str, type[NativeModel]] = {
    "session.start": SessionStartData,
    "session.resume": ResumeData,
    "session.error": SessionErrorData,
    "user.message": UserData,
    "system.message": SystemData,
    "assistant.message": AssistantData,
    "tool.execution_complete": ToolCompleteData,
    "tool.user_requested": UserToolRequestData,
    "session.compaction_complete": CompactionData,
    "session.truncation": TruncationData,
    "abort": NativeModel,
    "subagent.started": SubagentData,
    "subagent.completed": SubagentData,
    "subagent.failed": SubagentData,
    "system.notification": NotificationData,
    "skill.invoked": NoticeData,
    "skill.context_delivered": NoticeData,
    "skill.context_delivered_ref": SkillReferenceData,
    "session.mode_notice_delivered": NoticeData,
    "session.handoff": HandoffData,
}
_IGNORED_EVENTS = {
    "session.shutdown",
    "session.model_change",
    "session.info",
    "session.warning",
    "session.idle",
    "session.usage_info",
    "session.context_changed",
    "session.compaction_start",
    "hook.start",
    "hook.end",
    "assistant.turn_start",
    "assistant.turn_end",
    "assistant.message_delta",
    # Display-only reasoning events. Reasoning that stays in the model's context is
    # carried on assistant.message, which the converter records.
    "assistant.reasoning",
    "assistant.reasoning_delta",
    "assistant.usage",
    "tool.execution_start",
    "tool.execution_progress",
    "tool.execution_partial_result",
    # The prompt and decision are UI state; a denial reaches the model as a failed
    # tool result, which is recorded.
    "permission.requested",
    "permission.completed",
    "subagent.configured",
    "subagent.selected",
    "subagent.deselected",
    # Telemetry about interrupted work; the abort event carries what the transcript needs.
    "agent.interrupted",
    # A durable receipt whose content comes from an earlier skill.invoked event.
    "skill.invoked_ref",
    # UI, configuration and state notifications that put nothing in the model's context.
    "assistant.message_start",
    "assistant.streaming_delta",
    "assistant.tool_call_delta",
    "assistant.idle",
    "assistant.intent",
    "assistant.server_tool_progress",
    "assistant.turn_retry",
    "hook.progress",
    "sandbox.decision",
    "session.title_changed",
    "session.todos_changed",
    "session.tools_updated",
    "session.skills_loaded",
    "session.custom_agents_updated",
    "session.extensions_loaded",
    "session.mcp_servers_loaded",
    "session.mcp_server_status_changed",
    "session.mcp_server_needs_reconnect",
    "session.mcp_server_removed",
    "session.background_tasks_changed",
    "session.usage_checkpoint",
    "session.session_limits_changed",
    "session.permissions_changed",
    "session.permission_recovery",
    "session.managed_settings_enforced",
    "session.managed_settings_resolved",
    "session.remote_steerable_changed",
    "session.workspace_file_changed",
    "session.plan_changed",
    "session.memory_changed",
    "session.mode_changed",
    "session.model_deselected",
    "session.auto_mode_resolved",
    "session.auto_tier_recommendation",
    "session.auto_tier_switch_failed",
    "session.autopilot_objective_changed",
    "session.task_complete",
    "session.completion_receipt",
    "session.custom_notification",
    "capabilities.changed",
    "commands.changed",
    "command.queued",
    "command.execute",
    "command.completed",
    "pending_messages.modified",
    "ui.ephemeral_query",
    "tool_search.activated",
    "user_input.requested",
    "user_input.completed",
    "exit_plan_mode.requested",
    "exit_plan_mode.completed",
    "elicitation.requested",
    "elicitation.completed",
    "external_tool.requested",
    "external_tool.completed",
    "sampling.requested",
    "sampling.completed",
    "mcp.oauth_required",
    "mcp.oauth_completed",
    "mcp.headers_refresh_required",
    "mcp.headers_refresh_completed",
    "mcp.tools.list_changed",
    "mcp.prompts.list_changed",
    "mcp.resources.list_changed",
    "auto_mode_switch.requested",
    "auto_mode_switch.completed",
    "session_limits_exhausted.requested",
    "session_limits_exhausted.completed",
    # A schedule's prompt reaches the transcript as a user.message each time it fires.
    "session.schedule_created",
    "session.schedule_cancelled",
    "session.schedule_rearmed",
    "workflow.run_started",
    "workflow.run_updated",
    "workflow.run_settled",
    # A tool call made by an MCP app's own view, not by the agent.
    "mcp_app.tool_call_complete",
    # The bytes behind an attachment's assetId; descriptors are recorded instead.
    "session.binary_asset",
    # Canvas panels, extension attachments queued for a later message, search status
    # and the experimental HydraFusion bookkeeping. The model-visible fusion handoff is
    # not listed, so it gets an unsupported-event notice.
    "session.canvas.opened",
    "session.canvas.closed",
    "session.canvas.recorded",
    "session.canvas.removed",
    "session.canvas.registry_changed",
    "session.canvas.unavailable",
    "session.extensions.attachments_pushed",
    "session.indexed_search",
    "session.fusion_route_started",
    "session.fusion_route_failed",
    "session.fusion_resolved",
    "session.fusion_commit_started",
    "session.fusion_change_checkpoint",
    "session.fusion_completed",
}
# The error categories Copilot's event schema lists for a failed model request.
_MODEL_REQUEST_ERRORS = {"authentication", "authorization", "quota", "rate_limit", "context_limit", "query"}
# model.* events are telemetry about individual model calls (including the
# summarizer that performs compaction); the conversation itself is carried by the
# message events above.
_TELEMETRY_PREFIX = "model."


@dataclass(frozen=True)
class Event:
    """One event's type, the subagent it belongs to, and its data, which is ``None`` for an unknown type."""

    kind: str
    agent_id: str | None
    data: NativeModel | None


def parse_event(event: Mapping[str, JsonValue]) -> Event | None:
    """Ignore lifecycle events and mark unknown ones; refuse known events this sample cannot represent."""
    try:
        envelope = EventKind.model_validate(event)
        if envelope.type in _IGNORED_EVENTS or envelope.type.startswith(_TELEMETRY_PREFIX):
            return None
        model = _DATA.get(envelope.type)
        return Event(
            envelope.type, envelope.agentId, None if model is None else model.model_validate(event.get("data"))
        )
    except ValidationError as error:
        if any(item["type"] == "value_error" for item in error.errors(include_input=False, include_context=False)):
            raise UnsupportedTranscriptError("Unsupported Copilot content") from None
        raise TranscriptError("Malformed Copilot event") from None


@dataclass(frozen=True)
class SubagentHistory:
    agent_id: str
    messages: list[dict[str, JsonValue]]


# The reason the gate gives Copilot when Watcher escalates. Copilot repeats it in
# the permission request it records, which identifies the prompts the gate caused.
ESCALATION_MESSAGE = "Watcher asks you to approve this call"


@dataclass(frozen=True)
class HumanResponse:
    """A person's answer to a prompt the gate raised for one recorded parent tool call.

    ``tool_name`` and ``arguments`` are the call as recorded. ``decision`` is
    ``"allow"`` or ``"deny"``; ``decided_at`` is Copilot's timestamp for the
    answer, and ``completed`` says whether the call's result has been recorded.
    """

    tool_use_id: str
    tool_name: str
    arguments: dict[str, JsonValue]
    decision: Literal["allow", "deny"]
    decided_at: str | None
    completed: bool


@dataclass(frozen=True)
class ConvertedSession:
    """The parent conversation plus every subagent conversation ready to record.

    Messages from ``turn_start`` on follow the parent's second-to-last final answer:
    at a completed turn, they are the turn's messages and those of any turn that
    ended without an answer.
    ``replied`` is set once the parent has answered, or reported an error, at least once.
    ``human_responses`` are the answers people gave to the gate's prompts for the
    parent's recorded calls; see ``human_responses``.
    ``skipped_events`` counts events left out of any conversation, each place
    marked by ``SKIPPED_EVENT_NOTICE``.
    """

    messages: list[dict[str, JsonValue]]
    subagents: list[SubagentHistory]
    turn_start: int = 0
    replied: bool = False
    human_responses: list[HumanResponse] = field(default_factory=list)
    skipped_events: int = 0


def human_responses(
    events: Sequence[Mapping[str, JsonValue]], messages: Sequence[Mapping[str, JsonValue]]
) -> list[HumanResponse]:
    """Answers to the gate's escalation prompts for calls in the recorded ``messages``.

    Copilot records a hook's prompt as ``permission.requested`` with
    ``permissionRequest.kind == "hook"`` and the hook's message, and the answer as
    ``permission.completed`` with the same ``requestId``. Only prompts carrying
    ``ESCALATION_MESSAGE`` count, so prompts from other hooks and Copilot's own
    permission prompts are ignored. Only an answer whose ``decisionSource`` is
    ``human_response`` is a person's: Copilot gives a host policy's, an
    assisted-approval judge's or an unattended fallback's answer the same
    ``result``, and older completions have no source. Copilot's ``approved``
    becomes ``allow`` and ``denied-interactively-by-user`` becomes ``deny``. Other answers, such as a
    prompt cancelled because the session ended or one Copilot denied because it
    could not ask, and calls not in ``messages`` (such as a subagent's), are left
    out.

    The log is agent-writable, so another process can append prompts and answers
    to it, before or after the real ones. Every answer logged for a prompt's
    request counts, wherever it appears, and identical answers count as one. A
    call is left out when its prompts or answers disagree: one request prompting
    for two calls, an answer naming another call than its prompt, or answers of
    different kinds or sources for the call. A forged approval then cancels the person's real
    denial, or Copilot's own denial when it could not ask, instead of replacing
    it. Answers that agree, as when two installs' gates prompt for one call, keep
    the first one's time. Recording also checks each answer against the calls the gate
    itself escalated before uploading it.
    """
    calls: dict[str, Mapping[str, JsonValue]] = {}
    results: set[str] = set()
    for message in messages:
        tool_calls = message.get("tool_calls")
        if isinstance(tool_calls, list):
            for call in tool_calls:
                if isinstance(call, dict) and isinstance(call_id := call.get("id"), str):
                    calls[call_id] = call
        if message.get("role") == "tool" and isinstance(result_id := message.get("tool_call_id"), str):
            results.add(result_id)
    # The call each gate prompt asked about, and every answer logged for each request
    # wherever it appears in the log, by request ID.
    prompted: dict[str, str] = {}
    replies: dict[str, list[Mapping[str, JsonValue]]] = {}
    disputed: set[str] = set()
    for event in events:
        data = event.get("data")
        if not isinstance(data, dict):
            continue
        request_id = data.get("requestId")
        if not isinstance(request_id, str):
            continue
        if event.get("type") == "permission.requested":
            request = data.get("permissionRequest")
            if (
                isinstance(request, dict)
                and request.get("kind") == "hook"
                and request.get("hookMessage") == ESCALATION_MESSAGE
                and isinstance(call_id := request.get("toolCallId"), str)
            ):
                earlier = prompted.setdefault(request_id, call_id)
                if earlier != call_id:
                    disputed |= {earlier, call_id}
        elif event.get("type") == "permission.completed":
            replies.setdefault(request_id, []).append(event)
    answers: dict[str, list[Mapping[str, JsonValue]]] = {}
    for request_id, call_id in prompted.items():
        answered = replies.get(request_id, [])
        others = {named for item in answered if (named := _answered_call(item)) is not None and named != call_id}
        if others or len({_answer(item) for item in answered}) > 1:
            disputed |= {call_id, *others}
        elif answered:
            answers.setdefault(call_id, []).extend(answered)
    responses: list[HumanResponse] = []
    for call_id, answered in answers.items():
        distinct = {_answer(item) for item in answered}
        call = calls.get(call_id)
        if call_id in disputed or call is None or len(distinct) != 1:
            continue
        [(kind, source)] = distinct
        if source != "human_response" or kind not in ("approved", "denied-interactively-by-user"):
            continue
        arguments = call.get("arguments")
        timestamp = answered[0].get("timestamp")
        responses.append(
            HumanResponse(
                tool_use_id=call_id,
                tool_name=str(call.get("function")),
                arguments=arguments if isinstance(arguments, dict) else {},
                decision="allow" if kind == "approved" else "deny",
                decided_at=timestamp if isinstance(timestamp, str) else None,
                completed=call_id in results,
            )
        )
    return responses


def _answered_call(event: Mapping[str, JsonValue]) -> str | None:
    """The ``toolCallId`` a ``permission.completed`` event names, or ``None`` when it names none."""
    data = event.get("data")
    named = data.get("toolCallId") if isinstance(data, dict) else None
    return named if isinstance(named, str) else None


def _answer(event: Mapping[str, JsonValue]) -> tuple[str | None, str | None]:
    """A ``permission.completed`` event's ``result.kind`` and ``decisionSource``, each ``None`` unless text."""
    data = event.get("data")
    result = data.get("result") if isinstance(data, dict) else None
    kind = result.get("kind") if isinstance(result, dict) else None
    source = data.get("decisionSource") if isinstance(data, dict) else None
    return (kind if isinstance(kind, str) else None, source if isinstance(source, str) else None)


@dataclass
class _Conversation:
    messages: list[dict[str, JsonValue]] = field(default_factory=list)
    system_count: int = 0
    replied: bool = False
    calls: dict[str, str] = field(default_factory=dict)
    completed: set[str] = field(default_factory=set)
    interrupted: set[str] = field(default_factory=set)
    unknown: set[str] = field(default_factory=set)
    skipped: int = 0

    def skip(self) -> None:
        """Leave out one event, marking the place; consecutive skipped events share one notice.

        Sharing keeps a run of broken lines from filling the history, and stays
        deterministic, so a later snapshot of the same log still extends this one.
        """
        self.skipped += 1
        if not self.messages or self.messages[-1].get("metadata") != _SKIPPED_METADATA:
            # Sharing the metadata object is safe: _storable_messages copies every message.
            self.messages.append(_notice(SKIPPED_EVENT_NOTICE, _SKIPPED_METADATA))

    def open_calls(self, deadline: float | None) -> list[str]:
        calls: list[str] = []
        for call in self.calls:
            check_deadline(deadline)
            if call not in self.completed:
                calls.append(call)
        return calls

    def interrupt(self, deadline: float | None) -> None:
        """Give every call still open here Copilot's interrupted result."""
        for call in self.open_calls(deadline):
            check_deadline(deadline)
            self.completed.add(call)
            self.interrupted.add(call)
            self.messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call,
                    "function": self.calls[call],
                    "content": INTERRUPTED,
                    "error": {"type": "unknown", "message": INTERRUPTED},
                }
            )


def _bounded(text: str) -> str:
    if len(text) <= MAX_TOOL_TEXT:
        return text
    return (
        text[:MAX_TOOL_TEXT]
        + f"\n[Watcher recorded the first {MAX_TOOL_TEXT} of {len(text)} characters of this result.]"
    )


def convert_session(
    events: Sequence[Mapping[str, JsonValue]], *, final: bool = False, deadline: float | None = None
) -> ConvertedSession:
    """Convert the parent conversation and every finished subagent conversation to Inspect messages.

    Streaming and lifecycle events are ignored. An event type this sample does not
    know is marked by a notice where it first appears, so missing context is never
    presented as a complete conversation; known content it cannot represent, such as
    provider-hosted tools, is refused with ``UnsupportedTranscriptError``. An event
    it cannot read is left out and its place marked by ``SKIPPED_EVENT_NOTICE``:
    an unreadable line, malformed fields, a message reusing an earlier tool-call ID,
    or a result with no unanswered call of its ID. Recording then continues.
    Initial system instructions move before the first user message; later
    instructions and all user, assistant and tool messages retain their order.
    Each tool result must follow its request, matched by native ID. A request
    whose result has not appeared yet stays unanswered; when the result appears
    later, a later snapshot adds it, so recorded snapshots keep extending.
    An ``abort`` event gives the aborted conversation's open calls Copilot's
    interrupted result.
    Supply events in native order. A user's ``transformedContent``, when present,
    is the model-facing prompt and takes precedence over their original text.
    Tool result ``content`` is model-facing; UI-only details are not messages.
    Freeform tools such as ``apply_patch`` become ``custom`` tool calls whose
    raw text input is kept under ``arguments.input``. Tool calls and results carry
    the Claude Code names from ``policy_call``, as the gate submits them.
    Readable ``reasoningText`` becomes a redacted reasoning block before the
    assistant's text. Encrypted reasoning, signatures and provider reasoning
    copies carry no readable content and are not recorded.
    Events with an ``agentId`` belong to subagents and are returned separately
    from the parent conversation. A successful compaction appends Copilot's
    summary and Watcher's compaction notice, and earlier messages stay in place,
    so each snapshot extends the previous one.

    A subagent is included once Copilot records it as completed or failed, or for
    any subagent when ``final`` is set because the session has ended. A finished
    subagent's unanswered tool calls stay unanswered rather than being invented.
    An optional absolute ``time.monotonic()`` deadline stops conversion with ``TimeoutError``.
    The result also carries people's answers to the gate's prompts; see ``human_responses``.
    """
    return _convert(events, None, final=final, deadline=deadline)


def _binary_block(item: Mapping[str, JsonValue]) -> dict[str, JsonValue]:
    """Describe one attachment or binary result by Copilot's own descriptor, without its bytes.

    The descriptor names the file, type, size and content hash. Bytes are left out:
    the Analyzer shows them as raw base64, graders cannot read them, and the whole
    history is resent on every turn within Watcher's request size limit. Inline
    bytes get the identity Copilot gives persisted assets: ``assetId`` is
    ``sha256:`` plus the digest of the bytes, and ``byteLength`` their size.
    """
    descriptor: dict[str, JsonValue] = {key: value for key, value in item.items() if key != "data"}
    inline = item.get("data")
    if isinstance(inline, str):
        raw = _decode_inline(inline)
        if raw is None:
            # The bytes are never recorded, so undecodable data is marked rather than
            # refused; refusing would stop every later recording of this session.
            descriptor.setdefault("omittedReason", "undecodable")
        else:
            descriptor.setdefault("assetId", "sha256:" + hashlib.sha256(raw).hexdigest())
            descriptor.setdefault("byteLength", len(raw))
    return {"type": "data", "data": descriptor}


def _decode_inline(value: str) -> bytes | None:
    """Decode base64 that may be line-wrapped or carry a ``data:`` URI prefix."""
    if value.startswith("data:") and "," in value:
        value = value.split(",", 1)[1]
    try:
        return base64.b64decode("".join(value.split()), validate=True)
    except (binascii.Error, ValueError):
        return None


def storable(value: JsonValue, *, deadline: float | None = None) -> JsonValue:
    """The value without NUL characters, which Watcher strips before storing, so readback can match."""
    check_deadline(deadline)
    if isinstance(value, str):
        return value.replace("\x00", "")
    if isinstance(value, list):
        return [storable(item, deadline=deadline) for item in value]
    if isinstance(value, dict):
        return {key.replace("\x00", ""): storable(item, deadline=deadline) for key, item in value.items()}
    return value


def _storable_messages(messages: list[dict[str, JsonValue]], deadline: float | None) -> list[dict[str, JsonValue]]:
    converted = [_MESSAGE.validate_python(storable(message, deadline=deadline)) for message in messages]
    check_deadline(deadline)
    return converted


def _notice(text: str, metadata: dict[str, JsonValue]) -> dict[str, JsonValue]:
    return {"role": "system", "content": text, "metadata": metadata}


def _convert(
    events: Sequence[Mapping[str, JsonValue]], session_id: UUID | None, *, final: bool, deadline: float | None
) -> ConvertedSession:
    check_deadline(deadline)
    parent = _Conversation()
    agents: dict[str, _Conversation] = {}
    finished: set[str] = set()
    delegations: dict[str, str] = {}
    skills: dict[str, str] = {}
    user_commands: dict[str, str] = {}
    seen_start = False
    turn_start = last_answer = 0
    for raw_event in events:
        check_deadline(deadline)
        if raw_event.get("type") == UNREADABLE_EVENT:
            parent.skip()
            continue
        try:
            event = parse_event(raw_event)
        except UnsupportedTranscriptError:
            raise
        except TranscriptError:
            # Malformed fields: the event is left out of the conversation it names.
            owner = raw_event.get("agentId")
            (agents.setdefault(owner, _Conversation()) if isinstance(owner, str) and owner else parent).skip()
            continue
        if event is None:
            continue
        kind, agent_id, data = event.kind, event.agent_id, event.data
        conversation = parent if agent_id is None else agents.setdefault(agent_id, _Conversation())
        if data is None:
            # Copilot adds event types often. One this sample does not know might carry
            # content, so where it first appears is marked instead of silently dropped,
            # and recording continues. Marking only the first keeps a frequent new event
            # from filling the history. Event types are Copilot's own names, not user content.
            if kind not in conversation.unknown:
                conversation.unknown.add(kind)
                conversation.messages.append(
                    _notice(
                        f"[UNSUPPORTED EVENT NOTICE]\nCopilot recorded {kind[:80]} events from here on, "
                        "which this integration does not record.\n[END NOTICE]",
                        {"github_copilot_cli": {"unsupported_event": kind[:80]}},
                    )
                )
        elif agent_id is None and isinstance(data, MessageData) and data.parentToolCallId:
            raise UnsupportedTranscriptError("Subagent content without an agent identity is unsupported")
        elif isinstance(data, SessionStartData):
            # Only the log's own first session.start names its session; a handoff can
            # later replay another session's events, including its session.start.
            if agent_id is None and session_id is not None and not seen_start and data.sessionId != session_id:
                raise TranscriptError("Copilot transcript session does not match the callback")
            seen_start = True
        elif isinstance(data, HandoffData):
            # Work handed over from another Copilot session, such as a cloud agent.
            parts = [data.summary] if data.summary else []
            if isinstance(data.context, str) and data.context:
                parts.append(data.context)
            if parts:
                conversation.messages.append(
                    {
                        "role": "user",
                        "content": "\n\n".join(parts),
                        "metadata": {
                            "github_copilot_cli": {
                                "handoff": {
                                    "source_type": data.sourceType,
                                    "remote_session_id": data.remoteSessionId,
                                }
                            }
                        },
                    }
                )
        elif kind == "skill.invoked" and isinstance(data, NoticeData):
            skills["sha256:" + hashlib.sha256(data.content.encode()).hexdigest()] = data.content
        elif isinstance(data, SkillReferenceData):
            # The model receives the skill as a user message: this event's prefix and
            # suffix around the content of the skill.invoked event it references.
            if data.contentId not in skills:
                conversation.skip()
                continue
            content = data.prefix + skills[data.contentId] + data.suffix
            conversation.messages.append({"role": "user", "content": content})
        elif isinstance(data, NoticeData) and not isinstance(data, NotificationData):
            conversation.messages.append({"role": "user", "content": data.content})
        elif isinstance(data, NotificationData):
            conversation.messages.append(
                {
                    "role": "user",
                    "content": data.content,
                    "metadata": {"github_copilot_cli": {"notification": data.kind.type}},
                }
            )
        elif isinstance(data, SubagentData):
            if agent_id is None:
                parent.skip()
                continue
            if kind == "subagent.started":
                delegations[data.toolCallId] = agent_id
            else:
                finished.add(agent_id)
        elif kind == "abort":
            # An abort ends the turn of the conversation it names: the parent when it has
            # no agentId, otherwise that subagent. Calls still open there never return,
            # so they get an explicit interrupted result. Other conversations keep their
            # open calls, which may still complete.
            conversation.interrupt(deadline)
        elif isinstance(data, UserToolRequestData):
            user_commands[data.toolCallId] = data.arguments.command
        elif isinstance(data, ToolCompleteData) and data.toolCallId in user_commands:
            # Copilot shows the model a user's own shell command as this user message.
            # A failed or cancelled command reads "non-zero exit code", whatever the code.
            status = "exit code 0" if data.success else "non-zero exit code"
            output = data.result.content if data.success and data.result else data.error.message if data.error else ""
            conversation.messages.append(
                {
                    "role": "user",
                    "content": "<user_shell_command_output>\nThe user executed a shell command directly in their "
                    f"terminal ({status}).\n\nCommand:\n{user_commands.pop(data.toolCallId)}\n\n"
                    f"Output:\n{_bounded(output)}\n</user_shell_command_output>",
                }
            )
        elif isinstance(data, ResumeData) and not (
            data.alreadyInUse or data.sessionWasActive or data.continuePendingWork
        ):
            # A resumed session runs in a new process. Calls and subagents still open in
            # the process that ended, for example after a crash, can never finish. A
            # resume that joins a session another client is still running, or that
            # continues its pending work and waits for their results, changes nothing.
            for stopped in (parent, *agents.values()):
                check_deadline(deadline)
                stopped.interrupt(deadline)
            finished.update(agents)
        elif isinstance(data, SessionErrorData):
            # A failed model request ends the turn without a reply. The notice records
            # the failure, and later system instructions are appended after it rather
            # than moved before the first prompt, which a stored history must not change.
            # Other errors, such as a failed lookup of provider labels on resume, leave
            # the conversation unchanged and are not recorded.
            if data.errorType not in _MODEL_REQUEST_ERRORS:
                continue
            status = f", HTTP {data.statusCode}" if data.statusCode is not None else ""
            conversation.messages.append(
                _notice(
                    f"[ERROR NOTICE]\nCopilot reported an error ({data.errorType}{status}).\n[END NOTICE]",
                    {"github_copilot_cli": {"error": {"type": data.errorType, "status_code": data.statusCode}}},
                )
            )
            conversation.replied = True
        elif isinstance(data, CompactionData):
            if data.success:
                if data.summaryContent is None:
                    conversation.skip()
                    continue
                boundary: dict[str, JsonValue] = {"harness": "github-copilot-cli"}
                if data.checkpointNumber is not None:
                    boundary["window"] = data.checkpointNumber
                conversation.messages.append({"role": "user", "content": data.summaryContent})
                conversation.messages.append(_notice(COMPACTION_NOTICE, {"compaction_boundary": boundary}))
        elif isinstance(data, TruncationData):
            removed = data.messagesRemovedDuringTruncation
            conversation.messages.append(
                _notice(
                    "[TRUNCATION NOTICE]\n"
                    f"Copilot removed {removed} earlier messages from the agent's context at this point.\n"
                    "[END NOTICE]",
                    {"github_copilot_cli": {"truncation": {"messages_removed": removed}}},
                )
            )
        elif isinstance(data, SystemData):
            if data.contentBlocks and "\n\n".join(block.content for block in data.contentBlocks) != data.content:
                raise UnsupportedTranscriptError("System content blocks do not match the text transcript")
            system: dict[str, JsonValue] = {"role": "system", "content": data.content}
            if conversation.replied:
                conversation.messages.append(system)
            else:
                conversation.messages.insert(conversation.system_count, system)
                conversation.system_count += 1
        elif isinstance(data, UserData):
            content = data.transformedContent if "transformedContent" in data.model_fields_set else data.content
            user_content: JsonValue = content
            if data.attachments:
                user_content = [
                    {"type": "text", "text": content},
                    *(_binary_block(attachment) for attachment in data.attachments),
                ]
            conversation.messages.append({"role": "user", "content": user_content})
        elif isinstance(data, AssistantData):
            call_ids = [call.toolCallId for call in data.toolRequests]
            if len(set(call_ids)) < len(call_ids) or any(call_id in conversation.calls for call_id in call_ids):
                # Results and the gate find a call by its native ID, so a repeated ID
                # would make two calls indistinguishable. The whole message is left
                # out, and results for its calls are then left out as unmatched.
                conversation.skip()
                continue
            conversation.replied = True
            assistant_content: JsonValue = data.content
            if (data.reasoningText or "").strip():
                # Providers usually expose only a summary of their reasoning. Recording it
                # as a redacted block's summary matches how Watcher stores Claude Code
                # thinking, and it is the text the Analyzer displays.
                blocks: list[JsonValue] = [
                    {"type": "reasoning", "reasoning": "", "summary": data.reasoningText, "redacted": True}
                ]
                if data.content:
                    blocks.append({"type": "text", "text": data.content})
                assistant_content = blocks
            message: dict[str, JsonValue] = {"role": "assistant", "content": assistant_content}
            pending: list[JsonValue] = []
            for call in data.toolRequests:
                check_deadline(deadline)
                if isinstance(call, CustomToolRequest):
                    function, arguments = policy_call(call.name, {"input": call.arguments})
                    conversation.calls[call.toolCallId] = function
                    pending.append(
                        {"id": call.toolCallId, "function": function, "arguments": arguments, "type": "custom"}
                    )
                else:
                    function, arguments = policy_call(call.name, call.arguments)
                    conversation.calls[call.toolCallId] = function
                    pending.append({"id": call.toolCallId, "function": function, "arguments": arguments})
            if pending:
                message["tool_calls"] = pending
            elif conversation is parent and (
                (data.chunkIndex, data.chunkCount) == (None, None)
                or (data.chunkIndex is not None and data.chunkIndex + 1 == data.chunkCount)
            ):
                # A final answer ends a turn, so the calls after the one before this
                # belong to the latest turn, including calls made before a steering
                # prompt and calls of turns that were aborted or failed. A response
                # split into chunks at reasoning boundaries ends with its last chunk;
                # with incomplete chunk fields the boundary stays, so no call is skipped.
                turn_start, last_answer = last_answer, len(parent.messages) + 1
            conversation.messages.append(message)
        elif isinstance(data, ToolCompleteData) and data.toolCallId in conversation.interrupted:
            # The model was already given the interrupted result, which stays recorded.
            pass
        elif isinstance(data, ToolCompleteData):
            if data.toolCallId not in conversation.calls or data.toolCallId in conversation.completed:
                # No earlier call has this ID, or its result is already recorded.
                conversation.skip()
                continue
            tool_content: JsonValue
            if data.success:
                if data.result is None:
                    conversation.skip()
                    continue
                result = _bounded(data.result.content)
                extras: list[JsonValue] = [_binary_block(item) for item in data.result.binaryResultsForLlm or []]
                if data.result.citableSources:
                    extras.append({"type": "data", "data": {"citableSources": data.result.citableSources}})
                tool_content = [{"type": "text", "text": result}, *extras] if extras else result
            else:
                if data.error is None:
                    conversation.skip()
                    continue
                result = _bounded(data.error.message)
                tool_content = result
            conversation.completed.add(data.toolCallId)
            tool_message: dict[str, JsonValue] = {
                "role": "tool",
                "tool_call_id": data.toolCallId,
                "function": conversation.calls[data.toolCallId],
                "content": tool_content,
            }
            if not data.success:
                tool_message["error"] = {"type": "unknown", "message": result}
            if agent_id is None and data.toolCallId in delegations:
                # Links the delegation result to the subagent's own Watcher session.
                # Metadata is not part of message identity and is never updated, so it
                # must be present from the first submission, which it is: Copilot logs
                # subagent.started before the delegation's result.
                tool_message["metadata"] = {"github_copilot_cli": {"subagent_agent_id": delegations[data.toolCallId]}}
            conversation.messages.append(tool_message)
    messages = _storable_messages(parent.messages, deadline)
    return ConvertedSession(
        messages,
        [
            SubagentHistory(agent_id, _storable_messages(conversation.messages, deadline))
            for agent_id, conversation in agents.items()
            # Like the parent, a subagent is recorded only once it has replied: until
            # then its system instructions can still arrive ahead of its first user
            # message, which would reorder the start of a stored history.
            if (final or agent_id in finished) and conversation.replied
        ],
        turn_start,
        parent.replied,
        # Every reader goes through here, including the observer's, so recording
        # always sees people's answers to the gate's prompts.
        human_responses=human_responses(events, messages),
        skipped_events=parent.skipped + sum(conversation.skipped for conversation in agents.values()),
    )


def read_transcript(payload: Mapping[str, JsonValue]) -> list[dict[str, JsonValue]]:
    """Read only the event log identified by this native session's agentStop hook.

    The path must match Copilot's configured state directory. The 256 MiB limit
    refuses an oversized history rather than sending an incomplete prefix.
    Requires ``sessionId`` and ``transcriptPath`` from the native callback and
    checks the file's session identity. This immediate read does not wait for
    the final answer; callbacks should use ``wait_for_completed_session``.
    ``COPILOT_HOME`` selects the state directory; its default is ``~/.copilot``.
    """
    turn = _completed_turn(payload)
    return _convert(
        read_events(turn.sessionId, turn.transcriptPath), turn.sessionId, final=False, deadline=None
    ).messages


def is_subagent_stop(payload: Mapping[str, JsonValue]) -> bool:
    """Whether an agentStop callback reports a subagent finishing rather than the parent's turn.

    Copilot also runs agentStop hooks when a subagent ends, sending the subagent's
    agent ID as ``sessionId`` alongside the parent's transcript path. The parent is
    still mid-turn then, so there is nothing new to record; its own agentStop and
    sessionEnd callbacks record the subagent. Any other mismatch is an error.
    """
    turn = _completed_turn(payload)
    path = Path(turn.transcriptPath)
    if path.parent.name == str(turn.sessionId):
        return False
    try:
        parent = UUID(path.parent.name)
    except ValueError:
        raise TranscriptError("Unsupported transcript path or size") from None
    events = read_events(parent, path, allow_partial_tail=True)
    if any(EventKind.model_validate(event).agentId == str(turn.sessionId) for event in events):
        return True
    raise TranscriptError("Copilot callback session does not match its transcript")


def _completed_turn(payload: Mapping[str, JsonValue]) -> CompletedTurn:
    try:
        return CompletedTurn.model_validate(payload)
    except ValidationError:
        raise TranscriptError("Malformed Copilot turn-completion callback") from None


def session_state_dir() -> Path:
    """The directory holding one folder per session; ``COPILOT_HOME`` selects its parent, ``~/.copilot`` by default."""
    return copilot_home() / "session-state"


def session_transcript_path(session_id: UUID) -> Path:
    return session_state_dir() / str(session_id) / "events.jsonl"


def _lines(path: Path, deadline: float | None, max_event_bytes: int | None) -> Iterator[bytes]:
    check_deadline(deadline)
    with path.open("rb") as stream:
        total = 0
        while True:
            check_deadline(deadline)
            line = stream.readline(-1 if max_event_bytes is None else max_event_bytes + 1)
            check_deadline(deadline)
            if not line:
                return
            if max_event_bytes is not None and len(line) > max_event_bytes:
                raise UnsupportedTranscriptError("Copilot transcript event exceeds the hook read limit")
            total += len(line)
            if total > MAX_TRANSCRIPT_BYTES:
                raise TranscriptError("Unsupported transcript path or size")
            yield line


def read_events(
    session_id: UUID,
    transcript_path: str | Path,
    *,
    allow_partial_tail: bool = False,
    deadline: float | None = None,
    max_event_bytes: int | None = None,
) -> list[dict[str, JsonValue]]:
    """Read Copilot's log, dropping model telemetry. ``allow_partial_tail`` skips a line still being written.

    A complete line that is not an event, such as broken JSON or an object without
    a type, becomes an event of type ``UNREADABLE_EVENT`` in its place, which the
    converter marks with ``SKIPPED_EVENT_NOTICE``, so one bad line never stops
    recording. Only an unfinished final line, without its newline, is retried.
    An optional absolute ``time.monotonic()`` deadline stops reading with ``TimeoutError``.
    ``max_event_bytes`` bounds each read before JSON parsing, including its newline.
    Larger events raise ``UnsupportedTranscriptError``; ordinary recording leaves the ceiling unset.
    """
    check_deadline(deadline)
    expected = session_transcript_path(session_id).resolve(strict=True)
    path = Path(transcript_path).resolve(strict=True)
    if path != expected or not path.is_file():
        raise TranscriptError("Unsupported transcript path or size")
    events: list[dict[str, JsonValue]] = []
    for line in _lines(path, deadline, max_event_bytes):
        if not line.strip():
            continue
        try:
            event = JSON_OBJECT.validate_json(line)
            EventKind.model_validate(event)
        except ValidationError as error:
            is_partial_line = not line.endswith(b"\n")
            is_invalid_json = any(
                item["type"] == "json_invalid" for item in error.errors(include_input=False, include_context=False)
            )
            if is_partial_line and is_invalid_json:
                if allow_partial_tail:
                    break
                raise IncompleteTranscriptError("Copilot transcript ends with an incomplete JSON event") from None
            events.append({"type": UNREADABLE_EVENT})
            continue
        # Model-call telemetry can dwarf the conversation (it snapshots every request),
        # so it is dropped while reading instead of being held for the whole session.
        kind = event.get("type")
        if not (isinstance(kind, str) and kind.startswith(_TELEMETRY_PREFIX)):
            events.append(event)
    check_deadline(deadline)
    return events


def _ends_turn(messages: list[dict[str, JsonValue]]) -> bool:
    """A final assistant answer, or a compaction notice when the turn was only ``/compact``.

    Notices this sample adds for unsupported events, errors and truncation may follow it.
    """
    for message in reversed(messages):
        metadata = message.get("metadata")
        if message["role"] == "system" and isinstance(metadata, dict) and "github_copilot_cli" in metadata:
            continue
        if message["role"] == "assistant":
            return "tool_calls" not in message
        return message["role"] == "system" and isinstance(metadata, dict) and "compaction_boundary" in metadata
    return False


def _has_completed_turn(
    events: Sequence[Mapping[str, JsonValue]], messages: list[dict[str, JsonValue]], turn: CompletedTurn
) -> bool:
    """Whether the log shows the callback's own turn as finished.

    A malformed turn boundary or agentStop marker, or a turn end that matches no
    started turn, is ignored rather than refused, as the converter skips such
    events, so one bad line cannot stop every later turn from being recorded.
    """
    if not _ends_turn(messages):
        return False
    has_turn_boundaries = False
    is_turn_complete = False
    active_turn_id: str | None = None
    has_callback_marker = turn.timestamp is None
    for event in events:
        try:
            envelope = EventKind.model_validate(event)
            if envelope.agentId is not None:
                # A subagent's turns interleave with the parent's and reuse turn IDs;
                # only the parent's turns decide whether the callback's turn is done.
                continue
            kind = envelope.type
            if kind == "user.message":
                is_turn_complete = False
            elif kind in {"assistant.turn_start", "assistant.turn_end"}:
                boundary = TurnBoundaryEvent.model_validate(event)
                has_turn_boundaries = True
                if boundary.type == "assistant.turn_start":
                    active_turn_id = boundary.data.turnId
                    is_turn_complete = False
                elif active_turn_id == boundary.data.turnId:
                    is_turn_complete = True
                    active_turn_id = None
            elif kind == "hook.start" and turn.timestamp is not None:
                hook = HookKindEvent.model_validate(event)
                if hook.data.hookType == "agentStop":
                    callback = AgentStopEvent.model_validate(event).data.input
                    if callback.sessionId == turn.sessionId and callback.timestamp == turn.timestamp:
                        has_callback_marker = is_turn_complete
        except ValidationError:
            continue
    return has_callback_marker and (is_turn_complete or not has_turn_boundaries)


async def wait_for_completed_session(payload: Mapping[str, JsonValue], timeout_seconds: float) -> ConvertedSession:
    """Wait up to five seconds for a completed turn to reach Copilot's event log.

    A native callback's timestamp binds the read to its own persisted agentStop
    marker, so an earlier resumed turn cannot be mistaken for the new answer.
    Replay without a callback timestamp requires the latest turn to be closed.
    Partial final JSON lines and unfinished writes are retried within the bound;
    complete malformed events and unsupported content fail immediately.
    """
    if not math.isfinite(timeout_seconds) or not 0 < timeout_seconds <= 5:
        raise ValueError("Transcript wait must be greater than zero and at most five seconds")
    turn = _completed_turn(payload)
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_seconds
    while True:
        try:
            events = read_events(turn.sessionId, turn.transcriptPath)
            session = _convert(events, turn.sessionId, final=False, deadline=None)
            if _has_completed_turn(events, session.messages, turn):
                return session
        except (IncompleteTranscriptError, FileNotFoundError):
            pass
        remaining = deadline - loop.time()
        if remaining <= 0:
            raise IncompleteTranscriptError("Copilot transcript did not finish writing before the deadline")
        await asyncio.sleep(min(0.1, remaining))


def _compaction_running(events: Sequence[Mapping[str, JsonValue]]) -> bool:
    """Whether the current invocation's latest compaction has started but not yet finished.

    A compaction left unfinished by an earlier invocation that exited or crashed
    never completes, so a later start, resume or shutdown clears it.
    """
    running = False
    for event in events:
        envelope = EventKind.model_validate(event)
        if envelope.agentId is not None:
            continue
        if envelope.type == "session.compaction_start":
            running = True
        elif envelope.type in {"session.compaction_complete", "session.start", "session.resume", "session.shutdown"}:
            running = False
    return running


async def read_ended_session(
    payload: Mapping[str, JsonValue], timeout_seconds: float, *, compaction_seconds: float = 15
) -> ConvertedSession:
    """Read the session as it stands now, including every subagent.

    Used when a session ends and for replay. In prompt mode Copilot fires
    ``sessionEnd`` after every invocation and the session can continue later, so
    unanswered calls and running subagents are recorded as they stand and later
    snapshots extend them. A partially written final line is retried for up to
    ``timeout_seconds`` (at most five). A background compaction that is still
    running, which Copilot finishes while this hook runs, is awaited for up to
    ``compaction_seconds`` so its summary is not left out of the final snapshot.
    """
    if not math.isfinite(timeout_seconds) or not 0 < timeout_seconds <= 5:
        raise ValueError("Transcript wait must be greater than zero and at most five seconds")
    try:
        ended = SessionEnded.model_validate(payload)
    except ValidationError:
        raise TranscriptError("Malformed Copilot session-end callback") from None
    path = session_transcript_path(ended.sessionId)
    loop = asyncio.get_running_loop()
    started = loop.time()
    # One overall bound covers both waits, so a line still being written late in a
    # compaction wait (often the compaction result itself) is retried, not refused.
    limit = max(timeout_seconds, compaction_seconds)
    while True:
        elapsed = loop.time() - started
        try:
            events = read_events(ended.sessionId, path)
            if not _compaction_running(events) or elapsed >= compaction_seconds:
                return _convert(events, ended.sessionId, final=True, deadline=None)
        except IncompleteTranscriptError:
            if elapsed >= limit:
                raise
        await asyncio.sleep(0.1)
