from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Self, TypeVar
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="SpawnedSubagent")


@_attrs_define
class SpawnedSubagent:
    """A readable child linked to an exact spawning call in this trajectory.

    Match both the message reference and tool-use ID when rendering. The same
    native call ID may occur on other stored branches without this association.

        Attributes:
            session_id (UUID):
            spawning_message_trajectory_hash (str):
            spawning_tool_use_id (str):
    """

    session_id: UUID
    spawning_message_trajectory_hash: str
    spawning_tool_use_id: str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        session_id = str(self.session_id)

        spawning_message_trajectory_hash = self.spawning_message_trajectory_hash

        spawning_tool_use_id = self.spawning_tool_use_id

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "session_id": session_id,
                "spawning_message_trajectory_hash": spawning_message_trajectory_hash,
                "spawning_tool_use_id": spawning_tool_use_id,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        d = dict(src_dict)
        session_id = UUID(d.pop("session_id"))

        spawning_message_trajectory_hash = d.pop("spawning_message_trajectory_hash")

        spawning_tool_use_id = d.pop("spawning_tool_use_id")

        spawned_subagent = cls(
            session_id=session_id,
            spawning_message_trajectory_hash=spawning_message_trajectory_hash,
            spawning_tool_use_id=spawning_tool_use_id,
        )

        spawned_subagent.additional_properties = d
        return spawned_subagent

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
