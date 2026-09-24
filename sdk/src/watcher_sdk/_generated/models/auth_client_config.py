from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.auth_client_config_auth_mode import AuthClientConfigAuthMode
from ..types import UNSET, Unset

T = TypeVar("T", bound="AuthClientConfig")


@_attrs_define
class AuthClientConfig:
    """Response from GET /v1/auth/client-config.

    Public (unauthenticated) deployment auth descriptor: lets browser SPAs
    and CLI/hook clients discover how to authenticate against this server
    from nothing but its URL. ``workos_client_id`` is non-None only in
    WorkOS auth mode. Client IDs are public by construction (they appear
    in every authorize URL), so exposing one here leaks nothing.

        Attributes:
            auth_mode (AuthClientConfigAuthMode):
            workos_client_id (None | str | Unset):
    """

    auth_mode: AuthClientConfigAuthMode
    workos_client_id: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        auth_mode = self.auth_mode.value

        workos_client_id: None | str | Unset
        if isinstance(self.workos_client_id, Unset):
            workos_client_id = UNSET
        else:
            workos_client_id = self.workos_client_id

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "auth_mode": auth_mode,
            }
        )
        if workos_client_id is not UNSET:
            field_dict["workos_client_id"] = workos_client_id

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        auth_mode = AuthClientConfigAuthMode(d.pop("auth_mode"))

        def _parse_workos_client_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        workos_client_id = _parse_workos_client_id(d.pop("workos_client_id", UNSET))

        auth_client_config = cls(
            auth_mode=auth_mode,
            workos_client_id=workos_client_id,
        )

        auth_client_config.additional_properties = d
        return auth_client_config

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
