from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Self, TypeVar, cast
from uuid import UUID

from attrs import define as _attrs_define

from ..types import UNSET, Unset

T = TypeVar("T", bound="AgentRelationshipRequest")


@_attrs_define
class AgentRelationshipRequest:
    """Create a child's parent link or fill previously unknown spawning details.

    Omitted or null details leave existing values unchanged. Parent and resolved
    spawning details are immutable. A message hash requires its tool-use ID.
    Without a hash, the server looks up the native call in the parent's stored
    messages, selecting the first inserted match if representations repeat.
    Missing calls leave the hash unresolved; retry after ordinary ingestion.
    Both sessions must already exist.

        Attributes:
            parent_session_id (UUID):
            spawning_tool_use_id (None | str | Unset):
            spawning_message_trajectory_hash (None | str | Unset):
    """

    parent_session_id: UUID
    spawning_tool_use_id: None | str | Unset = UNSET
    spawning_message_trajectory_hash: None | str | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        parent_session_id = str(self.parent_session_id)

        spawning_tool_use_id: None | str | Unset
        if isinstance(self.spawning_tool_use_id, Unset):
            spawning_tool_use_id = UNSET
        else:
            spawning_tool_use_id = self.spawning_tool_use_id

        spawning_message_trajectory_hash: None | str | Unset
        if isinstance(self.spawning_message_trajectory_hash, Unset):
            spawning_message_trajectory_hash = UNSET
        else:
            spawning_message_trajectory_hash = self.spawning_message_trajectory_hash

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "parent_session_id": parent_session_id,
            }
        )
        if spawning_tool_use_id is not UNSET:
            field_dict["spawning_tool_use_id"] = spawning_tool_use_id
        if spawning_message_trajectory_hash is not UNSET:
            field_dict["spawning_message_trajectory_hash"] = (
                spawning_message_trajectory_hash
            )

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        d = dict(src_dict)
        parent_session_id = UUID(d.pop("parent_session_id"))

        def _parse_spawning_tool_use_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        spawning_tool_use_id = _parse_spawning_tool_use_id(
            d.pop("spawning_tool_use_id", UNSET)
        )

        def _parse_spawning_message_trajectory_hash(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        spawning_message_trajectory_hash = _parse_spawning_message_trajectory_hash(
            d.pop("spawning_message_trajectory_hash", UNSET)
        )

        agent_relationship_request = cls(
            parent_session_id=parent_session_id,
            spawning_tool_use_id=spawning_tool_use_id,
            spawning_message_trajectory_hash=spawning_message_trajectory_hash,
        )

        return agent_relationship_request
