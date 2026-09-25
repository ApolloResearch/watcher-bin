from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.auth_user import AuthUser


T = TypeVar("T", bound="DeviceTokenResponse")


@_attrs_define
class DeviceTokenResponse:
    """Response from POST /v1/auth/device/token once the user approved the login.

    Unlike ``TokenResponse``, the refresh token travels in the JSON body: the
    caller is a CLI with its own on-disk credential store, not a browser, so
    there is no cookie jar to hide it in.

        Attributes:
            access_token (str):
            refresh_token (str):
            user (AuthUser): The signed-in user's identity as login endpoints report it.

                ``id`` is the WorkOS user id; ``user_id`` is Watcher's own user id, present
                once the login has created or matched the Watcher user (it can be absent
                only when WorkOS reported no email to match by).
    """

    access_token: str
    refresh_token: str
    user: AuthUser
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        access_token = self.access_token

        refresh_token = self.refresh_token

        user = self.user.to_dict()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "access_token": access_token,
                "refresh_token": refresh_token,
                "user": user,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.auth_user import AuthUser

        d = dict(src_dict)
        access_token = d.pop("access_token")

        refresh_token = d.pop("refresh_token")

        user = AuthUser.from_dict(d.pop("user"))

        device_token_response = cls(
            access_token=access_token,
            refresh_token=refresh_token,
            user=user,
        )

        device_token_response.additional_properties = d
        return device_token_response

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
