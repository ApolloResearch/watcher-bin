from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from typing_extensions import Self

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.hook_append_anchor import HookAppendAnchor


T = TypeVar("T", bound="IngestResponse")


@_attrs_define
class IngestResponse:
    """Response from the full ingest and per-session append endpoints.

    ``trajectory_ids`` includes newly stored leaves and echoes of existing
    leaves: empty appends, recognized append replays, and exact full-ingest
    duplicates. Successful appends return their committed or echoed endpoint
    in ``append_anchor``.

    ``ingested_count`` and ``duplicate_count`` are in stored-leaf units, not
    uploaded files: a rewound Claude Code file stores one leaf per
    conversation branch, so one upload can produce several of either.

    ``append_anchor`` identifies the continuation of the final nonempty parsed
    input (the live branch of a rewound Claude Code file). Null means it has no
    usable leaf, for example because it ends inside a longer stored chain;
    do not advance the append cursor in that case.

    ``trajectory_ids`` still lists stored leaves in processing order for grading
    and queries. Neither its last ID nor the legacy representative ``session_id``
    selects the append anchor. Only responses from older servers that omit
    ``append_anchor`` use the legacy last-ID convention.

        Attributes:
            session_id (str):
            trajectory_ids (list[str]):
            ingested_count (int):
            duplicate_count (int):
            skipped_count (int):
            append_anchor (HookAppendAnchor | None | Unset):
    """

    session_id: str
    trajectory_ids: list[str]
    ingested_count: int
    duplicate_count: int
    skipped_count: int
    append_anchor: HookAppendAnchor | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.hook_append_anchor import HookAppendAnchor

        session_id = self.session_id

        trajectory_ids = self.trajectory_ids

        ingested_count = self.ingested_count

        duplicate_count = self.duplicate_count

        skipped_count = self.skipped_count

        append_anchor: dict[str, Any] | None | Unset
        if isinstance(self.append_anchor, Unset):
            append_anchor = UNSET
        elif isinstance(self.append_anchor, HookAppendAnchor):
            append_anchor = self.append_anchor.to_dict()
        else:
            append_anchor = self.append_anchor

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "session_id": session_id,
                "trajectory_ids": trajectory_ids,
                "ingested_count": ingested_count,
                "duplicate_count": duplicate_count,
                "skipped_count": skipped_count,
            }
        )
        if append_anchor is not UNSET:
            field_dict["append_anchor"] = append_anchor

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        from ..models.hook_append_anchor import HookAppendAnchor

        d = dict(src_dict)
        session_id = d.pop("session_id")

        trajectory_ids = cast(list[str], d.pop("trajectory_ids"))

        ingested_count = d.pop("ingested_count")

        duplicate_count = d.pop("duplicate_count")

        skipped_count = d.pop("skipped_count")

        def _parse_append_anchor(data: object) -> HookAppendAnchor | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                append_anchor_type_0 = HookAppendAnchor.from_dict(data)

                return append_anchor_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(HookAppendAnchor | None | Unset, data)

        append_anchor = _parse_append_anchor(d.pop("append_anchor", UNSET))

        ingest_response = cls(
            session_id=session_id,
            trajectory_ids=trajectory_ids,
            ingested_count=ingested_count,
            duplicate_count=duplicate_count,
            skipped_count=skipped_count,
            append_anchor=append_anchor,
        )

        ingest_response.additional_properties = d
        return ingest_response

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
