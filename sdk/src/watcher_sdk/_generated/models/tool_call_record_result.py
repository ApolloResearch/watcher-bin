from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Self, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.tool_call_content_state import ToolCallContentState
from ..models.tool_call_record_result_status import ToolCallRecordResultStatus

T = TypeVar("T", bound="ToolCallRecordResult")


@_attrs_define
class ToolCallRecordResult:
    """The outcome of one record, in request order after duplicates are merged.

    Attributes:
        tool_use_id (str): The record's tool_use_id.
        status (ToolCallRecordResultStatus): stored: Watcher now holds the call without content. linked: Watcher held
            the call's message, so the record became, or explained, an ordinary tool call linked to it. ignored_existing:
            nothing changed, because Watcher already held the call in a state the record cannot change, or retention removed
            the session's content and kept the call's outcome.
        content_state (ToolCallContentState): How much of a tool call Watcher holds.

            ``linked``: the call with the message that contains it. ``metadata_only``:
            only the call's ID, tool name and observation time, until its message
            arrives.
    """

    tool_use_id: str
    status: ToolCallRecordResultStatus
    content_state: ToolCallContentState
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        tool_use_id = self.tool_use_id

        status = self.status.value

        content_state = self.content_state.value

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "tool_use_id": tool_use_id,
                "status": status,
                "content_state": content_state,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        d = dict(src_dict)
        tool_use_id = d.pop("tool_use_id")

        status = ToolCallRecordResultStatus(d.pop("status"))

        content_state = ToolCallContentState(d.pop("content_state"))

        tool_call_record_result = cls(
            tool_use_id=tool_use_id,
            status=status,
            content_state=content_state,
        )

        tool_call_record_result.additional_properties = d
        return tool_call_record_result

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
