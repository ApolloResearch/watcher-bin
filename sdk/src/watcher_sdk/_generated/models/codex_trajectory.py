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
    from ..models.codex_entry import CodexEntry
    from ..models.codex_trajectory_metadata_type_0 import CodexTrajectoryMetadataType0
    from ..models.hook_append_anchor import HookAppendAnchor
    from ..models.ingest_tool_call_reference import IngestToolCallReference


T = TypeVar("T", bound="CodexTrajectory")


@_attrs_define
class CodexTrajectory:
    """One Codex thread's raw rollout events or delta.

    The first session_meta identifies this thread; later metadata can belong to
    inherited parent context. resolve_tool_calls names response-item IDs and
    call IDs in this upload, returning their stored message occurrences.

        Attributes:
            timestamp (datetime.datetime):
            format_ (Literal['codex-jsonl']):
            entries (list[CodexEntry]):
            session_id (None | str | Unset):
            metadata (CodexTrajectoryMetadataType0 | None | Unset):
            append_after (HookAppendAnchor | None | Unset):
            fork (bool | Unset):  Default: False.
            resolve_tool_calls (list[IngestToolCallReference] | Unset):
    """

    timestamp: datetime.datetime
    format_: Literal["codex-jsonl"]
    entries: list[CodexEntry]
    session_id: None | str | Unset = UNSET
    metadata: CodexTrajectoryMetadataType0 | None | Unset = UNSET
    append_after: HookAppendAnchor | None | Unset = UNSET
    fork: bool | Unset = False
    resolve_tool_calls: list[IngestToolCallReference] | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.codex_trajectory_metadata_type_0 import (
            CodexTrajectoryMetadataType0,
        )
        from ..models.hook_append_anchor import HookAppendAnchor

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
        elif isinstance(self.metadata, CodexTrajectoryMetadataType0):
            metadata = self.metadata.to_dict()
        else:
            metadata = self.metadata

        append_after: dict[str, Any] | None | Unset
        if isinstance(self.append_after, Unset):
            append_after = UNSET
        elif isinstance(self.append_after, HookAppendAnchor):
            append_after = self.append_after.to_dict()
        else:
            append_after = self.append_after

        fork = self.fork

        resolve_tool_calls: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.resolve_tool_calls, Unset):
            resolve_tool_calls = []
            for resolve_tool_calls_item_data in self.resolve_tool_calls:
                resolve_tool_calls_item = resolve_tool_calls_item_data.to_dict()
                resolve_tool_calls.append(resolve_tool_calls_item)

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
        if append_after is not UNSET:
            field_dict["append_after"] = append_after
        if fork is not UNSET:
            field_dict["fork"] = fork
        if resolve_tool_calls is not UNSET:
            field_dict["resolve_tool_calls"] = resolve_tool_calls

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        from ..models.codex_entry import CodexEntry
        from ..models.codex_trajectory_metadata_type_0 import (
            CodexTrajectoryMetadataType0,
        )
        from ..models.hook_append_anchor import HookAppendAnchor
        from ..models.ingest_tool_call_reference import IngestToolCallReference

        d = dict(src_dict)
        timestamp = datetime.datetime.fromisoformat(d.pop("timestamp"))

        format_ = cast(Literal["codex-jsonl"], d.pop("format"))
        if format_ != "codex-jsonl":
            raise ValueError(f"format must match const 'codex-jsonl', got '{format_}'")

        entries = []
        _entries = d.pop("entries")
        for entries_item_data in _entries:
            entries_item = CodexEntry.from_dict(entries_item_data)

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
        ) -> CodexTrajectoryMetadataType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                metadata_type_0 = CodexTrajectoryMetadataType0.from_dict(data)

                return metadata_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(CodexTrajectoryMetadataType0 | None | Unset, data)

        metadata = _parse_metadata(d.pop("metadata", UNSET))

        def _parse_append_after(data: object) -> HookAppendAnchor | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                append_after_type_0 = HookAppendAnchor.from_dict(data)

                return append_after_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(HookAppendAnchor | None | Unset, data)

        append_after = _parse_append_after(d.pop("append_after", UNSET))

        fork = d.pop("fork", UNSET)

        _resolve_tool_calls = d.pop("resolve_tool_calls", UNSET)
        resolve_tool_calls: list[IngestToolCallReference] | Unset = UNSET
        if _resolve_tool_calls is not UNSET:
            resolve_tool_calls = []
            for resolve_tool_calls_item_data in _resolve_tool_calls:
                resolve_tool_calls_item = IngestToolCallReference.from_dict(
                    resolve_tool_calls_item_data
                )

                resolve_tool_calls.append(resolve_tool_calls_item)

        codex_trajectory = cls(
            timestamp=timestamp,
            format_=format_,
            entries=entries,
            session_id=session_id,
            metadata=metadata,
            append_after=append_after,
            fork=fork,
            resolve_tool_calls=resolve_tool_calls,
        )

        codex_trajectory.additional_properties = d
        return codex_trajectory

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
