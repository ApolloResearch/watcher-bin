from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Self, TypeVar, cast
from uuid import UUID

from attrs import define as _attrs_define

from ..models.tool_call_records_request_agent_platform import (
    ToolCallRecordsRequestAgentPlatform,
)
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.tool_call_record import ToolCallRecord


T = TypeVar("T", bound="ToolCallRecordsRequest")


@_attrs_define
class ToolCallRecordsRequest:
    """Records of one agent session's ungraded tool calls.

    Attributes:
        agent_platform (ToolCallRecordsRequestAgentPlatform): The agent that made the calls: claude_code or codex. Other
            agents are rejected.
        agent_session_id (str): The agent's own conversation ID, the same one its transcript upload carries.
        records (list[ToolCallRecord]): The session's records, 1 to 500 per request. Repeated tool_use_ids count once.
        installation_id (None | Unset | UUID): The reporting Watcher client's installation ID (the one its installation
            reports carry). Stored with each new record when it names an installation the caller owns, so agent inventory
            can count a machine's records; otherwise ignored, never refused.
    """

    agent_platform: ToolCallRecordsRequestAgentPlatform
    agent_session_id: str
    records: list[ToolCallRecord]
    installation_id: None | Unset | UUID = UNSET

    def to_dict(self) -> dict[str, Any]:
        agent_platform = self.agent_platform.value

        agent_session_id = self.agent_session_id

        records = []
        for records_item_data in self.records:
            records_item = records_item_data.to_dict()
            records.append(records_item)

        installation_id: None | str | Unset
        if isinstance(self.installation_id, Unset):
            installation_id = UNSET
        elif isinstance(self.installation_id, UUID):
            installation_id = str(self.installation_id)
        else:
            installation_id = self.installation_id

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "agent_platform": agent_platform,
                "agent_session_id": agent_session_id,
                "records": records,
            }
        )
        if installation_id is not UNSET:
            field_dict["installation_id"] = installation_id

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        from ..models.tool_call_record import ToolCallRecord

        d = dict(src_dict)
        agent_platform = ToolCallRecordsRequestAgentPlatform(d.pop("agent_platform"))

        agent_session_id = d.pop("agent_session_id")

        records = []
        _records = d.pop("records")
        for records_item_data in _records:
            records_item = ToolCallRecord.from_dict(records_item_data)

            records.append(records_item)

        def _parse_installation_id(data: object) -> None | Unset | UUID:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                installation_id_type_0 = UUID(data)

                return installation_id_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | Unset | UUID, data)

        installation_id = _parse_installation_id(d.pop("installation_id", UNSET))

        tool_call_records_request = cls(
            agent_platform=agent_platform,
            agent_session_id=agent_session_id,
            records=records,
            installation_id=installation_id,
        )

        return tool_call_records_request
