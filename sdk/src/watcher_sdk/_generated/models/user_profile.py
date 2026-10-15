from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from typing_extensions import Self

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.user_profile_memberships_item import UserProfileMembershipsItem


T = TypeVar("T", bound="UserProfile")


@_attrs_define
class UserProfile:
    """Response from GET /v1/auth/me.

    Attributes:
        user_id (str):
        email (None | str | Unset):
        org_id (None | str | Unset):
        organization_id (None | str | Unset):
        organization_name (None | str | Unset):
        memberships (list[UserProfileMembershipsItem] | Unset):
        permissions (list[str] | Unset): Effective permission slugs for client UI gates: explicit grants plus known
            Watcher permissions granted by built-in roles. WorkOS widget permissions remain explicit.
        role (None | str | Unset): The caller's role in the active organization, for display only; gating belongs on
            ``permissions``, which includes built-in role grants. Under WorkOS this is the role the token names; proxy auth
            reports admin, org-viewer, or member. Null when the authentication in use vouches for no single role.
    """

    user_id: str
    email: None | str | Unset = UNSET
    org_id: None | str | Unset = UNSET
    organization_id: None | str | Unset = UNSET
    organization_name: None | str | Unset = UNSET
    memberships: list[UserProfileMembershipsItem] | Unset = UNSET
    permissions: list[str] | Unset = UNSET
    role: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        user_id = self.user_id

        email: None | str | Unset
        if isinstance(self.email, Unset):
            email = UNSET
        else:
            email = self.email

        org_id: None | str | Unset
        if isinstance(self.org_id, Unset):
            org_id = UNSET
        else:
            org_id = self.org_id

        organization_id: None | str | Unset
        if isinstance(self.organization_id, Unset):
            organization_id = UNSET
        else:
            organization_id = self.organization_id

        organization_name: None | str | Unset
        if isinstance(self.organization_name, Unset):
            organization_name = UNSET
        else:
            organization_name = self.organization_name

        memberships: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.memberships, Unset):
            memberships = []
            for memberships_item_data in self.memberships:
                memberships_item = memberships_item_data.to_dict()
                memberships.append(memberships_item)

        permissions: list[str] | Unset = UNSET
        if not isinstance(self.permissions, Unset):
            permissions = self.permissions

        role: None | str | Unset
        if isinstance(self.role, Unset):
            role = UNSET
        else:
            role = self.role

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "user_id": user_id,
            }
        )
        if email is not UNSET:
            field_dict["email"] = email
        if org_id is not UNSET:
            field_dict["org_id"] = org_id
        if organization_id is not UNSET:
            field_dict["organization_id"] = organization_id
        if organization_name is not UNSET:
            field_dict["organization_name"] = organization_name
        if memberships is not UNSET:
            field_dict["memberships"] = memberships
        if permissions is not UNSET:
            field_dict["permissions"] = permissions
        if role is not UNSET:
            field_dict["role"] = role

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        from ..models.user_profile_memberships_item import (
            UserProfileMembershipsItem,
        )

        d = dict(src_dict)
        user_id = d.pop("user_id")

        def _parse_email(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        email = _parse_email(d.pop("email", UNSET))

        def _parse_org_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        org_id = _parse_org_id(d.pop("org_id", UNSET))

        def _parse_organization_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        organization_id = _parse_organization_id(d.pop("organization_id", UNSET))

        def _parse_organization_name(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        organization_name = _parse_organization_name(d.pop("organization_name", UNSET))

        _memberships = d.pop("memberships", UNSET)
        memberships: list[UserProfileMembershipsItem] | Unset = UNSET
        if _memberships is not UNSET:
            memberships = []
            for memberships_item_data in _memberships:
                memberships_item = UserProfileMembershipsItem.from_dict(
                    memberships_item_data
                )

                memberships.append(memberships_item)

        permissions = cast(list[str], d.pop("permissions", UNSET))

        def _parse_role(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        role = _parse_role(d.pop("role", UNSET))

        user_profile = cls(
            user_id=user_id,
            email=email,
            org_id=org_id,
            organization_id=organization_id,
            organization_name=organization_name,
            memberships=memberships,
            permissions=permissions,
            role=role,
        )

        user_profile.additional_properties = d
        return user_profile

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
