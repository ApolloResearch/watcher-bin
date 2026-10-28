from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Self, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="AuthLogoutV1AuthLogoutPostResponseAuthLogoutV1AuthLogoutPost")


@_attrs_define
class AuthLogoutV1AuthLogoutPostResponseAuthLogoutV1AuthLogoutPost:
    additional_properties: dict[str, str] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        d = dict(src_dict)
        auth_logout_v1_auth_logout_post_response_auth_logout_v1_auth_logout_post = cls()

        auth_logout_v1_auth_logout_post_response_auth_logout_v1_auth_logout_post.additional_properties = d
        return auth_logout_v1_auth_logout_post_response_auth_logout_v1_auth_logout_post

    @property
    def additional_keys(self) -> list[str]:
        return list(self.additional_properties.keys())

    def __getitem__(self, key: str) -> str:
        return self.additional_properties[key]

    def __setitem__(self, key: str, value: str) -> None:
        self.additional_properties[key] = value

    def __delitem__(self, key: str) -> None:
        del self.additional_properties[key]

    def __contains__(self, key: str) -> bool:
        return key in self.additional_properties
