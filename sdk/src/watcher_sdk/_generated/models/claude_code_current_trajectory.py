from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import (
    TYPE_CHECKING,
    Any,
    Literal,
    Self,
    TypeVar,
    cast,
)

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.claude_code_agent_identity import ClaudeCodeAgentIdentity
    from ..models.claude_code_current_trajectory_metadata_type_0 import (
        ClaudeCodeCurrentTrajectoryMetadataType0,
    )
    from ..models.claude_code_entry import ClaudeCodeEntry


T = TypeVar("T", bound="ClaudeCodeCurrentTrajectory")


@_attrs_define
class ClaudeCodeCurrentTrajectory:
    """One ordered Claude conversation, supplied as context to the V1 hook.

    Clients select the active path with the shared Claude transport selector.
    Message order is authoritative; parent pointers are retained as native
    metadata, without reconstructing abandoned branches. Include compaction
    boundaries and queued-command aliases. The hook stores complete call
    cycles only, just as for a full file. Complete history still belongs to
    ingestion. Child requests require the same explicit agent identity as uploads.

        Attributes:
            timestamp (datetime.datetime):
            format_ (Literal['claude-code-trajectory']):
            entries (list[ClaudeCodeEntry]):
            session_id (None | str | Unset):
            metadata (ClaudeCodeCurrentTrajectoryMetadataType0 | None | Unset):
            agent (ClaudeCodeAgentIdentity | None | Unset):
    """

    timestamp: datetime.datetime
    format_: Literal["claude-code-trajectory"]
    entries: list[ClaudeCodeEntry]
    session_id: None | str | Unset = UNSET
    metadata: ClaudeCodeCurrentTrajectoryMetadataType0 | None | Unset = UNSET
    agent: ClaudeCodeAgentIdentity | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.claude_code_agent_identity import ClaudeCodeAgentIdentity
        from ..models.claude_code_current_trajectory_metadata_type_0 import (
            ClaudeCodeCurrentTrajectoryMetadataType0,
        )

        timestamp = self.timestamp.isoformat()

        format_ = self.format_

        entries = []
        for entries_item_data in self.entries:
            entries_item = entries_item_data.to_dict()
            entries.append(entries_item)

        session_id: None | str | Unset
        if isinstance(self.session_id, Unset):
            session_id = UNSET
        else:
            session_id = self.session_id

        metadata: dict[str, Any] | None | Unset
        if isinstance(self.metadata, Unset):
            metadata = UNSET
        elif isinstance(self.metadata, ClaudeCodeCurrentTrajectoryMetadataType0):
            metadata = self.metadata.to_dict()
        else:
            metadata = self.metadata

        agent: dict[str, Any] | None | Unset
        if isinstance(self.agent, Unset):
            agent = UNSET
        elif isinstance(self.agent, ClaudeCodeAgentIdentity):
            agent = self.agent.to_dict()
        else:
            agent = self.agent

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "timestamp": timestamp,
                "format": format_,
                "entries": entries,
            }
        )
        if session_id is not UNSET:
            field_dict["session_id"] = session_id
        if metadata is not UNSET:
            field_dict["metadata"] = metadata
        if agent is not UNSET:
            field_dict["agent"] = agent

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        from ..models.claude_code_agent_identity import ClaudeCodeAgentIdentity
        from ..models.claude_code_current_trajectory_metadata_type_0 import (
            ClaudeCodeCurrentTrajectoryMetadataType0,
        )
        from ..models.claude_code_entry import ClaudeCodeEntry

        d = dict(src_dict)
        timestamp = datetime.datetime.fromisoformat(d.pop("timestamp"))

        format_ = cast(Literal["claude-code-trajectory"], d.pop("format"))
        if format_ != "claude-code-trajectory":
            raise ValueError(
                f"format must match const 'claude-code-trajectory', got '{format_}'"
            )

        entries = []
        _entries = d.pop("entries")
        for entries_item_data in _entries:
            entries_item = ClaudeCodeEntry.from_dict(entries_item_data)

            entries.append(entries_item)

        def _parse_session_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        session_id = _parse_session_id(d.pop("session_id", UNSET))

        def _parse_metadata(
            data: object,
        ) -> ClaudeCodeCurrentTrajectoryMetadataType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                metadata_type_0 = ClaudeCodeCurrentTrajectoryMetadataType0.from_dict(
                    data
                )

                return metadata_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(ClaudeCodeCurrentTrajectoryMetadataType0 | None | Unset, data)

        metadata = _parse_metadata(d.pop("metadata", UNSET))

        def _parse_agent(data: object) -> ClaudeCodeAgentIdentity | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                agent_type_0 = ClaudeCodeAgentIdentity.from_dict(data)

                return agent_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(ClaudeCodeAgentIdentity | None | Unset, data)

        agent = _parse_agent(d.pop("agent", UNSET))

        claude_code_current_trajectory = cls(
            timestamp=timestamp,
            format_=format_,
            entries=entries,
            session_id=session_id,
            metadata=metadata,
            agent=agent,
        )

        claude_code_current_trajectory.additional_properties = d
        return claude_code_current_trajectory

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
