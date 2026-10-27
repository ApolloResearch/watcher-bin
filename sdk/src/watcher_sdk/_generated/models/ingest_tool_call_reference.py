from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from typing_extensions import Self

T = TypeVar("T", bound="IngestToolCallReference")


@_attrs_define
class IngestToolCallReference:
    """Ask an upload to resolve a tool call in a particular native transcript item.

    message_uuid is Claude's entry UUID or Codex's response-item ID.
    The entry must be included in this upload. Missing or filtered entries return
    no match; clients retain unresolved references for a later full upload.

        Attributes:
            message_uuid (str):
            tool_use_id (str):
    """

    message_uuid: str
    tool_use_id: str

    def to_dict(self) -> dict[str, Any]:
        message_uuid = self.message_uuid

        tool_use_id = self.tool_use_id

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "message_uuid": message_uuid,
                "tool_use_id": tool_use_id,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        d = dict(src_dict)
        message_uuid = d.pop("message_uuid")

        tool_use_id = d.pop("tool_use_id")

        ingest_tool_call_reference = cls(
            message_uuid=message_uuid,
            tool_use_id=tool_use_id,
        )

        return ingest_tool_call_reference
