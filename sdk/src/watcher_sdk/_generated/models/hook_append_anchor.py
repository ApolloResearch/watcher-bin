from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar
from uuid import UUID

from attrs import define as _attrs_define

T = TypeVar("T", bound="HookAppendAnchor")


@_attrs_define
class HookAppendAnchor:
    """The exact stored message after which a hook's delta begins.

    Obtain the first pair from session search or trajectory ingestion, then use
    the committed anchor returned by each successful hook append. An
    explicit session and trajectory disambiguate branches; the server never
    guesses which leaf the caller observed. A missing anchor returns 404 and
    a conflicting continuation returns 409. Retry once with the full transcript
    and without this field on 404, 409, or 422 (including older servers).

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
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        session_id = UUID(d.pop("session_id"))

        trajectory_id = d.pop("trajectory_id")

        hook_append_anchor = cls(
            session_id=session_id,
            trajectory_id=trajectory_id,
        )

        return hook_append_anchor
