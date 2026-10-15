from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import (
    TYPE_CHECKING,
    Any,
    Literal,
    TypeVar,
    cast,
)

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from typing_extensions import Self

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.copilot_entry import CopilotEntry
    from ..models.copilot_trajectory_metadata_type_0 import (
        CopilotTrajectoryMetadataType0,
    )


T = TypeVar("T", bound="CopilotTrajectory")


@_attrs_define
class CopilotTrajectory:
    """A trajectory in GitHub Copilot CLI format: one conversation's events from the session's events.jsonl.

    A Copilot log holds the parent conversation and every subagent's. Each
    upload carries one of them: ``agent_id`` is null for the parent
    conversation, or names the one subagent whose events ``entries`` holds,
    which Watcher records as its own session. ``agent_id`` is required, with
    null for the parent, so a subagent upload that leaves it out is refused
    rather than recorded as the parent.

        Attributes:
            timestamp (datetime.datetime):
            format_ (Literal['copilot-events-jsonl']):
            agent_id (None | str):
            entries (list[CopilotEntry]):
            session_id (None | str | Unset):
            metadata (CopilotTrajectoryMetadataType0 | None | Unset):
    """

    timestamp: datetime.datetime
    format_: Literal["copilot-events-jsonl"]
    agent_id: None | str
    entries: list[CopilotEntry]
    session_id: None | str | Unset = UNSET
    metadata: CopilotTrajectoryMetadataType0 | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.copilot_trajectory_metadata_type_0 import (
            CopilotTrajectoryMetadataType0,
        )

        timestamp = self.timestamp.isoformat()

        format_ = self.format_

        agent_id: None | str
        agent_id = self.agent_id

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
        elif isinstance(self.metadata, CopilotTrajectoryMetadataType0):
            metadata = self.metadata.to_dict()
        else:
            metadata = self.metadata

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "timestamp": timestamp,
                "format": format_,
                "agent_id": agent_id,
                "entries": entries,
            }
        )
        if session_id is not UNSET:
            field_dict["session_id"] = session_id
        if metadata is not UNSET:
            field_dict["metadata"] = metadata

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        from ..models.copilot_entry import CopilotEntry
        from ..models.copilot_trajectory_metadata_type_0 import (
            CopilotTrajectoryMetadataType0,
        )

        d = dict(src_dict)
        timestamp = datetime.datetime.fromisoformat(d.pop("timestamp"))

        format_ = cast(Literal["copilot-events-jsonl"], d.pop("format"))
        if format_ != "copilot-events-jsonl":
            raise ValueError(
                f"format must match const 'copilot-events-jsonl', got '{format_}'"
            )

        def _parse_agent_id(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        agent_id = _parse_agent_id(d.pop("agent_id"))

        entries = []
        _entries = d.pop("entries")
        for entries_item_data in _entries:
            entries_item = CopilotEntry.from_dict(entries_item_data)

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
        ) -> CopilotTrajectoryMetadataType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                metadata_type_0 = CopilotTrajectoryMetadataType0.from_dict(data)

                return metadata_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(CopilotTrajectoryMetadataType0 | None | Unset, data)

        metadata = _parse_metadata(d.pop("metadata", UNSET))

        copilot_trajectory = cls(
            timestamp=timestamp,
            format_=format_,
            agent_id=agent_id,
            entries=entries,
            session_id=session_id,
            metadata=metadata,
        )

        copilot_trajectory.additional_properties = d
        return copilot_trajectory

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
