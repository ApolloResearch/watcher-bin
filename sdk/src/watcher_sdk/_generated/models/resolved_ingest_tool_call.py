from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Self, TypeVar
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="ResolvedIngestToolCall")


@_attrs_define
class ResolvedIngestToolCall:
    """One stored call occurrence, scoped to a session and the uploaded branch.

    trajectory_hash is the end of the uploaded branch, which may now be a prefix
    of a longer stored trajectory. Select the intended branch when a reference
    has multiple matches; the server never chooses the latest occurrence.

        Attributes:
            session_id (UUID):
            message_uuid (str):
            tool_use_id (str):
            message_trajectory_hash (str):
            trajectory_hash (str):
    """

    session_id: UUID
    message_uuid: str
    tool_use_id: str
    message_trajectory_hash: str
    trajectory_hash: str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        session_id = str(self.session_id)

        message_uuid = self.message_uuid

        tool_use_id = self.tool_use_id

        message_trajectory_hash = self.message_trajectory_hash

        trajectory_hash = self.trajectory_hash

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "session_id": session_id,
                "message_uuid": message_uuid,
                "tool_use_id": tool_use_id,
                "message_trajectory_hash": message_trajectory_hash,
                "trajectory_hash": trajectory_hash,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        d = dict(src_dict)
        session_id = UUID(d.pop("session_id"))

        message_uuid = d.pop("message_uuid")

        tool_use_id = d.pop("tool_use_id")

        message_trajectory_hash = d.pop("message_trajectory_hash")

        trajectory_hash = d.pop("trajectory_hash")

        resolved_ingest_tool_call = cls(
            session_id=session_id,
            message_uuid=message_uuid,
            tool_use_id=tool_use_id,
            message_trajectory_hash=message_trajectory_hash,
            trajectory_hash=trajectory_hash,
        )

        resolved_ingest_tool_call.additional_properties = d
        return resolved_ingest_tool_call

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
