from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Self, TypeVar
from uuid import UUID

from attrs import define as _attrs_define

T = TypeVar("T", bound="HookAppendAnchor")


@_attrs_define
class HookAppendAnchor:
    """The exact stored message after which a delta begins.

    Ingest responses and successful hook appends return this session/trajectory
    pair for the next append. Keep both fields together: a session may contain
    several branches, and the server never guesses which leaf the caller observed.
    A later write can overtake the anchor; on an append conflict, reconcile with
    a full transcript upload before resuming deltas.

        Attributes:
            session_id (UUID):
            trajectory_id (str):
    """

    session_id: UUID
    trajectory_id: str

    def to_dict(self) -> dict[str, Any]:
        session_id = str(self.session_id)

        trajectory_id = self.trajectory_id

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "session_id": session_id,
                "trajectory_id": trajectory_id,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        d = dict(src_dict)
        session_id = UUID(d.pop("session_id"))

        trajectory_id = d.pop("trajectory_id")

        hook_append_anchor = cls(
            session_id=session_id,
            trajectory_id=trajectory_id,
        )

        return hook_append_anchor
