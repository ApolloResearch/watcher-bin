from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from dateutil.parser import isoparse

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.claude_api_message import ClaudeAPIMessage
    from ..models.claude_code_attachment import ClaudeCodeAttachment
    from ..models.tool_use_result import ToolUseResult


T = TypeVar("T", bound="ClaudeCodeEntry")


@_attrs_define
class ClaudeCodeEntry:
    """One entry from a Claude Code JSONL file.

    The JSONL contains many types: user, assistant, file-history-snapshot,
    progress, system, summary, attachment. We accept all types and filter to
    conversation-carrying entries (user/assistant with messages, plus
    queued-command attachments) during chain building.

        Attributes:
            type_ (str):
            uuid (None | str | Unset):
            parent_uuid (None | str | Unset):
            session_id (None | str | Unset):
            timestamp (datetime.datetime | None | Unset):
            message (ClaudeAPIMessage | None | Unset):
            attachment (ClaudeCodeAttachment | None | Unset):
            cwd (None | str | Unset):
            git_branch (None | str | Unset):
            version (None | str | Unset):
            user_type (None | str | Unset):
            is_sidechain (bool | Unset):  Default: False.
            is_compact_summary (bool | Unset):  Default: False.
            request_id (None | str | Unset):
            effort (None | str | Unset):
            tool_use_result (list[Any] | None | str | ToolUseResult | Unset):
            source_tool_assistant_uuid (None | str | Unset):
    """

    type_: str
    uuid: None | str | Unset = UNSET
    parent_uuid: None | str | Unset = UNSET
    session_id: None | str | Unset = UNSET
    timestamp: datetime.datetime | None | Unset = UNSET
    message: ClaudeAPIMessage | None | Unset = UNSET
    attachment: ClaudeCodeAttachment | None | Unset = UNSET
    cwd: None | str | Unset = UNSET
    git_branch: None | str | Unset = UNSET
    version: None | str | Unset = UNSET
    user_type: None | str | Unset = UNSET
    is_sidechain: bool | Unset = False
    is_compact_summary: bool | Unset = False
    request_id: None | str | Unset = UNSET
    effort: None | str | Unset = UNSET
    tool_use_result: list[Any] | None | str | ToolUseResult | Unset = UNSET
    source_tool_assistant_uuid: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.claude_api_message import ClaudeAPIMessage
        from ..models.claude_code_attachment import ClaudeCodeAttachment
        from ..models.tool_use_result import ToolUseResult

        type_ = self.type_

        uuid: None | str | Unset
        if isinstance(self.uuid, Unset):
            uuid = UNSET
        else:
            uuid = self.uuid

        parent_uuid: None | str | Unset
        if isinstance(self.parent_uuid, Unset):
            parent_uuid = UNSET
        else:
            parent_uuid = self.parent_uuid

        session_id: None | str | Unset
        if isinstance(self.session_id, Unset):
            session_id = UNSET
        else:
            session_id = self.session_id

        timestamp: None | str | Unset
        if isinstance(self.timestamp, Unset):
            timestamp = UNSET
        elif isinstance(self.timestamp, datetime.datetime):
            timestamp = self.timestamp.isoformat()
        else:
            timestamp = self.timestamp

        message: dict[str, Any] | None | Unset
        if isinstance(self.message, Unset):
            message = UNSET
        elif isinstance(self.message, ClaudeAPIMessage):
            message = self.message.to_dict()
        else:
            message = self.message

        attachment: dict[str, Any] | None | Unset
        if isinstance(self.attachment, Unset):
            attachment = UNSET
        elif isinstance(self.attachment, ClaudeCodeAttachment):
            attachment = self.attachment.to_dict()
        else:
            attachment = self.attachment

        cwd: None | str | Unset
        if isinstance(self.cwd, Unset):
            cwd = UNSET
        else:
            cwd = self.cwd

        git_branch: None | str | Unset
        if isinstance(self.git_branch, Unset):
            git_branch = UNSET
        else:
            git_branch = self.git_branch

        version: None | str | Unset
        if isinstance(self.version, Unset):
            version = UNSET
        else:
            version = self.version

        user_type: None | str | Unset
        if isinstance(self.user_type, Unset):
            user_type = UNSET
        else:
            user_type = self.user_type

        is_sidechain = self.is_sidechain

        is_compact_summary = self.is_compact_summary

        request_id: None | str | Unset
        if isinstance(self.request_id, Unset):
            request_id = UNSET
        else:
            request_id = self.request_id

        effort: None | str | Unset
        if isinstance(self.effort, Unset):
            effort = UNSET
        else:
            effort = self.effort

        tool_use_result: dict[str, Any] | list[Any] | None | str | Unset
        if isinstance(self.tool_use_result, Unset):
            tool_use_result = UNSET
        elif isinstance(self.tool_use_result, ToolUseResult):
            tool_use_result = self.tool_use_result.to_dict()
        elif isinstance(self.tool_use_result, list):
            tool_use_result = self.tool_use_result

        else:
            tool_use_result = self.tool_use_result

        source_tool_assistant_uuid: None | str | Unset
        if isinstance(self.source_tool_assistant_uuid, Unset):
            source_tool_assistant_uuid = UNSET
        else:
            source_tool_assistant_uuid = self.source_tool_assistant_uuid

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "type": type_,
            }
        )
        if uuid is not UNSET:
            field_dict["uuid"] = uuid
        if parent_uuid is not UNSET:
            field_dict["parentUuid"] = parent_uuid
        if session_id is not UNSET:
            field_dict["sessionId"] = session_id
        if timestamp is not UNSET:
            field_dict["timestamp"] = timestamp
        if message is not UNSET:
            field_dict["message"] = message
        if attachment is not UNSET:
            field_dict["attachment"] = attachment
        if cwd is not UNSET:
            field_dict["cwd"] = cwd
        if git_branch is not UNSET:
            field_dict["gitBranch"] = git_branch
        if version is not UNSET:
            field_dict["version"] = version
        if user_type is not UNSET:
            field_dict["userType"] = user_type
        if is_sidechain is not UNSET:
            field_dict["isSidechain"] = is_sidechain
        if is_compact_summary is not UNSET:
            field_dict["isCompactSummary"] = is_compact_summary
        if request_id is not UNSET:
            field_dict["requestId"] = request_id
        if effort is not UNSET:
            field_dict["effort"] = effort
        if tool_use_result is not UNSET:
            field_dict["toolUseResult"] = tool_use_result
        if source_tool_assistant_uuid is not UNSET:
            field_dict["sourceToolAssistantUUID"] = source_tool_assistant_uuid

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.claude_api_message import ClaudeAPIMessage
        from ..models.claude_code_attachment import ClaudeCodeAttachment
        from ..models.tool_use_result import ToolUseResult

        d = dict(src_dict)
        type_ = d.pop("type")

        def _parse_uuid(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        uuid = _parse_uuid(d.pop("uuid", UNSET))

        def _parse_parent_uuid(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        parent_uuid = _parse_parent_uuid(d.pop("parentUuid", UNSET))

        def _parse_session_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        session_id = _parse_session_id(d.pop("sessionId", UNSET))

        def _parse_timestamp(data: object) -> datetime.datetime | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                timestamp_type_0 = isoparse(data)

                return timestamp_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None | Unset, data)

        timestamp = _parse_timestamp(d.pop("timestamp", UNSET))

        def _parse_message(data: object) -> ClaudeAPIMessage | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                message_type_0 = ClaudeAPIMessage.from_dict(data)

                return message_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(ClaudeAPIMessage | None | Unset, data)

        message = _parse_message(d.pop("message", UNSET))

        def _parse_attachment(data: object) -> ClaudeCodeAttachment | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                attachment_type_0 = ClaudeCodeAttachment.from_dict(data)

                return attachment_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(ClaudeCodeAttachment | None | Unset, data)

        attachment = _parse_attachment(d.pop("attachment", UNSET))

        def _parse_cwd(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        cwd = _parse_cwd(d.pop("cwd", UNSET))

        def _parse_git_branch(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        git_branch = _parse_git_branch(d.pop("gitBranch", UNSET))

        def _parse_version(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        version = _parse_version(d.pop("version", UNSET))

        def _parse_user_type(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        user_type = _parse_user_type(d.pop("userType", UNSET))

        is_sidechain = d.pop("isSidechain", UNSET)

        is_compact_summary = d.pop("isCompactSummary", UNSET)

        def _parse_request_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        request_id = _parse_request_id(d.pop("requestId", UNSET))

        def _parse_effort(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        effort = _parse_effort(d.pop("effort", UNSET))

        def _parse_tool_use_result(
            data: object,
        ) -> list[Any] | None | str | ToolUseResult | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                tool_use_result_type_0 = ToolUseResult.from_dict(data)

                return tool_use_result_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            try:
                if not isinstance(data, list):
                    raise TypeError()
                tool_use_result_type_2 = cast(list[Any], data)

                return tool_use_result_type_2
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(list[Any] | None | str | ToolUseResult | Unset, data)

        tool_use_result = _parse_tool_use_result(d.pop("toolUseResult", UNSET))

        def _parse_source_tool_assistant_uuid(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        source_tool_assistant_uuid = _parse_source_tool_assistant_uuid(
            d.pop("sourceToolAssistantUUID", UNSET)
        )

        claude_code_entry = cls(
            type_=type_,
            uuid=uuid,
            parent_uuid=parent_uuid,
            session_id=session_id,
            timestamp=timestamp,
            message=message,
            attachment=attachment,
            cwd=cwd,
            git_branch=git_branch,
            version=version,
            user_type=user_type,
            is_sidechain=is_sidechain,
            is_compact_summary=is_compact_summary,
            request_id=request_id,
            effort=effort,
            tool_use_result=tool_use_result,
            source_tool_assistant_uuid=source_tool_assistant_uuid,
        )

        claude_code_entry.additional_properties = d
        return claude_code_entry

    @property
    def additional_keys(self) -> list[str]:
        return list(self.additional_properties.keys())

    def __getitem__(self, key: str) -> Any:
        return self.additional_properties[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self.additional_properties[key] = value

    def __delitem__(self, key: str) -> None:
        del self.additional_properties[key]

    def __contains__(self, key: str) -> bool:
        return key in self.additional_properties
