from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="IngestResponse")


@_attrs_define
class IngestResponse:
    """Response from the full ingest and per-session append endpoints.

    One shape for both paths keeps client bookkeeping (cursor advance, leaf
    tracking) shared. ``trajectory_ids`` echoes an already-stored leaf in two
    cases: an append whose delta parsed to zero messages, and a full ingest
    that exactly duplicates the caller's own session (which still counts
    toward ``duplicate_count``). Either way the client keeps a valid anchor
    for its next append.

    ``ingested_count`` and ``duplicate_count`` are in stored-leaf units, not
    uploaded files: a rewound Claude Code file stores one leaf per
    conversation branch, so one upload can produce several of either.

    ``trajectory_ids`` lists the resulting leaves in processing order — for a
    rewound Claude Code file, abandoned branches first and the live branch
    last, whether each leaf was newly stored or an echoed duplicate. The last
    entry is what clients record as their next append anchor, so live-last is
    a contract, not a coincidence of storage order.

        Attributes:
            session_id (str):
            trajectory_ids (list[str]):
            ingested_count (int):
            duplicate_count (int):
            skipped_count (int):
    """

    session_id: str
    trajectory_ids: list[str]
    ingested_count: int
    duplicate_count: int
    skipped_count: int
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        session_id = self.session_id

        trajectory_ids = self.trajectory_ids

        ingested_count = self.ingested_count

        duplicate_count = self.duplicate_count

        skipped_count = self.skipped_count

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

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        session_id = d.pop("session_id")

        trajectory_ids = cast(list[str], d.pop("trajectory_ids"))

        ingested_count = d.pop("ingested_count")

        duplicate_count = d.pop("duplicate_count")

        skipped_count = d.pop("skipped_count")

        ingest_response = cls(
            session_id=session_id,
            trajectory_ids=trajectory_ids,
            ingested_count=ingested_count,
            duplicate_count=duplicate_count,
            skipped_count=skipped_count,
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
