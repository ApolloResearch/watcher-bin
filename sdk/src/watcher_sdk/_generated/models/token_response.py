from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Self, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.token_response_user_type_0 import TokenResponseUserType0


T = TypeVar("T", bound="TokenResponse")


@_attrs_define
class TokenResponse:
    """Response from POST /v1/auth/callback and /v1/auth/refresh.

    The refresh token is only sent as an httpOnly ``Set-Cookie`` (``refresh_token``),
    not in this JSON body — browsers avoid exposing it to page JavaScript.
    Server-side clients read it from the cookie jar (e.g. httpx ``response.cookies``).

        Attributes:
            access_token (str):
            user (None | TokenResponseUserType0 | Unset):
    """

    access_token: str
    user: None | TokenResponseUserType0 | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.token_response_user_type_0 import TokenResponseUserType0

        access_token = self.access_token

        user: dict[str, Any] | None | Unset
        if isinstance(self.user, Unset):
            user = UNSET
        elif isinstance(self.user, TokenResponseUserType0):
            user = self.user.to_dict()
        else:
            user = self.user

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "access_token": access_token,
            }
        )
        if user is not UNSET:
            field_dict["user"] = user

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        from ..models.token_response_user_type_0 import TokenResponseUserType0

        d = dict(src_dict)
        access_token = d.pop("access_token")

        def _parse_user(data: object) -> None | TokenResponseUserType0 | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                user_type_0 = TokenResponseUserType0.from_dict(data)

                return user_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | TokenResponseUserType0 | Unset, data)

        user = _parse_user(d.pop("user", UNSET))

        token_response = cls(
            access_token=access_token,
            user=user,
        )

        token_response.additional_properties = d
        return token_response

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
