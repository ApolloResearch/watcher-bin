from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import Any, Self, TypeVar

from attrs import define as _attrs_define

from ..models.tool_call_skip_reason import ToolCallSkipReason

T = TypeVar("T", bound="ToolCallRecord")


@_attrs_define
class ToolCallRecord:
    """One tool call the client observed without grading it.

    Attributes:
        tool_use_id (str): The agent's own ID for the call, as its transcript records it.
        tool_name (str): The tool's name as the agent reported it.
        observed_at (datetime.datetime): When the client observed the call. A time in the future or before 2024 is
            replaced by the time Watcher received the record.
        skip_reason (ToolCallSkipReason): Why the Watcher client observed a tool call but did not grade it.

            Reported on a metadata-only tool-call record. ``unknown`` covers a client
            that could not name the cause.
    """

    tool_use_id: str
    tool_name: str
    observed_at: datetime.datetime
    skip_reason: ToolCallSkipReason

    def to_dict(self) -> dict[str, Any]:
        tool_use_id = self.tool_use_id

        tool_name = self.tool_name

        observed_at = self.observed_at.isoformat()

        skip_reason = self.skip_reason.value

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "tool_use_id": tool_use_id,
                "tool_name": tool_name,
                "observed_at": observed_at,
                "skip_reason": skip_reason,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        d = dict(src_dict)
        tool_use_id = d.pop("tool_use_id")

        tool_name = d.pop("tool_name")

        observed_at = datetime.datetime.fromisoformat(d.pop("observed_at"))

        skip_reason = ToolCallSkipReason(d.pop("skip_reason"))

        tool_call_record = cls(
            tool_use_id=tool_use_id,
            tool_name=tool_name,
            observed_at=observed_at,
            skip_reason=skip_reason,
        )

        return tool_call_record
