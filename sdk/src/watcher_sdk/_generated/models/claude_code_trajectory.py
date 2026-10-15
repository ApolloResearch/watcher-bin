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
    from ..models.claude_code_entry import ClaudeCodeEntry
    from ..models.claude_code_trajectory_metadata_type_0 import (
        ClaudeCodeTrajectoryMetadataType0,
    )


T = TypeVar("T", bound="ClaudeCodeTrajectory")


@_attrs_define
class ClaudeCodeTrajectory:
    """A Claude Code JSONL file or delta, with a stable conversation identity.

    ``session_id`` is the current Claude Code conversation ID, not a Watcher
    session UUID. Send the same value on full uploads and deltas: it takes
    precedence over historical ``sessionId`` values in copied entries. When
    omitted or empty, each parsed branch uses its first entry's ``sessionId``.
    Ownership checks still apply to the selected conversation, and hook
    appends must name the same conversation as their stored anchor.

        Attributes:
            timestamp (datetime.datetime):
            format_ (Literal['claude-code-jsonl']):
            entries (list[ClaudeCodeEntry]):
            session_id (None | str | Unset):
            metadata (ClaudeCodeTrajectoryMetadataType0 | None | Unset):
    """

    timestamp: datetime.datetime
    format_: Literal["claude-code-jsonl"]
    entries: list[ClaudeCodeEntry]
    session_id: None | str | Unset = UNSET
    metadata: ClaudeCodeTrajectoryMetadataType0 | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.claude_code_trajectory_metadata_type_0 import (
            ClaudeCodeTrajectoryMetadataType0,
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
        elif isinstance(self.metadata, ClaudeCodeTrajectoryMetadataType0):
            metadata = self.metadata.to_dict()
        else:
            metadata = self.metadata

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

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        from ..models.claude_code_entry import ClaudeCodeEntry
        from ..models.claude_code_trajectory_metadata_type_0 import (
            ClaudeCodeTrajectoryMetadataType0,
        )

        d = dict(src_dict)
        timestamp = datetime.datetime.fromisoformat(d.pop("timestamp"))

        format_ = cast(Literal["claude-code-jsonl"], d.pop("format"))
        if format_ != "claude-code-jsonl":
            raise ValueError(
                f"format must match const 'claude-code-jsonl', got '{format_}'"
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
        ) -> ClaudeCodeTrajectoryMetadataType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                metadata_type_0 = ClaudeCodeTrajectoryMetadataType0.from_dict(data)

                return metadata_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(ClaudeCodeTrajectoryMetadataType0 | None | Unset, data)

        metadata = _parse_metadata(d.pop("metadata", UNSET))

        claude_code_trajectory = cls(
            timestamp=timestamp,
            format_=format_,
            entries=entries,
            session_id=session_id,
            metadata=metadata,
        )

        claude_code_trajectory.additional_properties = d
        return claude_code_trajectory

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
