from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar
from uuid import UUID

from attrs import define as _attrs_define

T = TypeVar("T", bound="CreateSessionContentAccessRequest")


@_attrs_define
class CreateSessionContentAccessRequest:
    """Request content access to a known session; identity comes from authentication.

    Attributes:
        session_id (UUID):
    """

    session_id: UUID

    def to_dict(self) -> dict[str, Any]:
        session_id = str(self.session_id)

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "session_id": session_id,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        session_id = UUID(d.pop("session_id"))

        create_session_content_access_request = cls(
            session_id=session_id,
        )

        return create_session_content_access_request
