from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from typing_extensions import Self

from ..models.session_content_access_request_status import (
    SessionContentAccessRequestStatus,
)

if TYPE_CHECKING:
    from ..models.user_list_item import UserListItem


T = TypeVar("T", bound="AdminSessionContentAccessRequest")


@_attrs_define
class AdminSessionContentAccessRequest:
    """An organization request with its requester, reviewer, and revoker identities.

    Attributes:
        id (UUID):
        requested_session_id (UUID):
        status (SessionContentAccessRequestStatus): Stored request lifecycle; expiry is derived from the approval's
            validity window.
        raised_at (datetime.datetime):
        reviewed_at (datetime.datetime | None):
        valid_until (datetime.datetime | None):
        revoked_at (datetime.datetime | None):
        requesting_user (UserListItem): Per-user row exposed in ``GET /v1/users`` list responses.

            Includes ``email``: listing requires the ``users:read:any`` permission,
            which is also the permission that gates reading other users' emails, so
            every caller who can list users may see them.
        reviewed_by_user (None | UserListItem):
        revoked_by_user (None | UserListItem):
    """

    id: UUID
    requested_session_id: UUID
    status: SessionContentAccessRequestStatus
    raised_at: datetime.datetime
    reviewed_at: datetime.datetime | None
    valid_until: datetime.datetime | None
    revoked_at: datetime.datetime | None
    requesting_user: UserListItem
    reviewed_by_user: None | UserListItem
    revoked_by_user: None | UserListItem
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.user_list_item import UserListItem

        id = str(self.id)

        requested_session_id = str(self.requested_session_id)

        status = self.status.value

        raised_at = self.raised_at.isoformat()

        reviewed_at: None | str
        if isinstance(self.reviewed_at, datetime.datetime):
            reviewed_at = self.reviewed_at.isoformat()
        else:
            reviewed_at = self.reviewed_at

        valid_until: None | str
        if isinstance(self.valid_until, datetime.datetime):
            valid_until = self.valid_until.isoformat()
        else:
            valid_until = self.valid_until

        revoked_at: None | str
        if isinstance(self.revoked_at, datetime.datetime):
            revoked_at = self.revoked_at.isoformat()
        else:
            revoked_at = self.revoked_at

        requesting_user = self.requesting_user.to_dict()

        reviewed_by_user: dict[str, Any] | None
        if isinstance(self.reviewed_by_user, UserListItem):
            reviewed_by_user = self.reviewed_by_user.to_dict()
        else:
            reviewed_by_user = self.reviewed_by_user

        revoked_by_user: dict[str, Any] | None
        if isinstance(self.revoked_by_user, UserListItem):
            revoked_by_user = self.revoked_by_user.to_dict()
        else:
            revoked_by_user = self.revoked_by_user

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "id": id,
                "requested_session_id": requested_session_id,
                "status": status,
                "raised_at": raised_at,
                "reviewed_at": reviewed_at,
                "valid_until": valid_until,
                "revoked_at": revoked_at,
                "requesting_user": requesting_user,
                "reviewed_by_user": reviewed_by_user,
                "revoked_by_user": revoked_by_user,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        from ..models.user_list_item import UserListItem

        d = dict(src_dict)
        id = UUID(d.pop("id"))

        requested_session_id = UUID(d.pop("requested_session_id"))

        status = SessionContentAccessRequestStatus(d.pop("status"))

        raised_at = datetime.datetime.fromisoformat(d.pop("raised_at"))

        def _parse_reviewed_at(data: object) -> datetime.datetime | None:
            if data is None:
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                reviewed_at_type_0 = datetime.datetime.fromisoformat(data)

                return reviewed_at_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None, data)

        reviewed_at = _parse_reviewed_at(d.pop("reviewed_at"))

        def _parse_valid_until(data: object) -> datetime.datetime | None:
            if data is None:
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                valid_until_type_0 = datetime.datetime.fromisoformat(data)

                return valid_until_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None, data)

        valid_until = _parse_valid_until(d.pop("valid_until"))

        def _parse_revoked_at(data: object) -> datetime.datetime | None:
            if data is None:
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                revoked_at_type_0 = datetime.datetime.fromisoformat(data)

                return revoked_at_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None, data)

        revoked_at = _parse_revoked_at(d.pop("revoked_at"))

        requesting_user = UserListItem.from_dict(d.pop("requesting_user"))

        def _parse_reviewed_by_user(data: object) -> None | UserListItem:
            if data is None:
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                reviewed_by_user_type_0 = UserListItem.from_dict(data)

                return reviewed_by_user_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | UserListItem, data)

        reviewed_by_user = _parse_reviewed_by_user(d.pop("reviewed_by_user"))

        def _parse_revoked_by_user(data: object) -> None | UserListItem:
            if data is None:
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                revoked_by_user_type_0 = UserListItem.from_dict(data)

                return revoked_by_user_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | UserListItem, data)

        revoked_by_user = _parse_revoked_by_user(d.pop("revoked_by_user"))

        admin_session_content_access_request = cls(
            id=id,
            requested_session_id=requested_session_id,
            status=status,
            raised_at=raised_at,
            reviewed_at=reviewed_at,
            valid_until=valid_until,
            revoked_at=revoked_at,
            requesting_user=requesting_user,
            reviewed_by_user=reviewed_by_user,
            revoked_by_user=revoked_by_user,
        )

        admin_session_content_access_request.additional_properties = d
        return admin_session_content_access_request

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
