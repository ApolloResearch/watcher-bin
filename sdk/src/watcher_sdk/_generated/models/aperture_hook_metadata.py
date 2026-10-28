from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Self, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="ApertureHookMetadata")


@_attrs_define
class ApertureHookMetadata:
    """Tailscale Aperture-owned identity fields; unknown additions are accepted.

    ``request_id`` identifies a capture, never a conversation. ``session_id``
    is Aperture's own session id: one it took from the client (prefix
    ``xsid_`` or ``pisn_``) is recorded as the conversation id of a capture
    without a native one, and any other value is ignored. The provider key
    and URL describe routing and do not identify the developer's harness.
    ``user_agent`` supplies application evidence to the format parser. The
    parser applies the supported harness's marker and system-identity rules;
    selecting a wire format alone never admits an application. These fields
    classify captured traffic; they do not authenticate the caller.

        Attributes:
            login_name (str):
            request_id (str):
            provider (str):
            url (str):
            session_id (None | str | Unset):
            stable_node_id (None | str | Unset):
            user_agent (None | str | Unset):
    """

    login_name: str
    request_id: str
    provider: str
    url: str
    session_id: None | str | Unset = UNSET
    stable_node_id: None | str | Unset = UNSET
    user_agent: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        login_name = self.login_name

        request_id = self.request_id

        provider = self.provider

        url = self.url

        session_id: None | str | Unset
        if isinstance(self.session_id, Unset):
            session_id = UNSET
        else:
            session_id = self.session_id

        stable_node_id: None | str | Unset
        if isinstance(self.stable_node_id, Unset):
            stable_node_id = UNSET
        else:
            stable_node_id = self.stable_node_id

        user_agent: None | str | Unset
        if isinstance(self.user_agent, Unset):
            user_agent = UNSET
        else:
            user_agent = self.user_agent

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "login_name": login_name,
                "request_id": request_id,
                "provider": provider,
                "url": url,
            }
        )
        if session_id is not UNSET:
            field_dict["session_id"] = session_id
        if stable_node_id is not UNSET:
            field_dict["stable_node_id"] = stable_node_id
        if user_agent is not UNSET:
            field_dict["user_agent"] = user_agent

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        d = dict(src_dict)
        login_name = d.pop("login_name")

        request_id = d.pop("request_id")

        provider = d.pop("provider")

        url = d.pop("url")

        def _parse_session_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        session_id = _parse_session_id(d.pop("session_id", UNSET))

        def _parse_stable_node_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        stable_node_id = _parse_stable_node_id(d.pop("stable_node_id", UNSET))

        def _parse_user_agent(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        user_agent = _parse_user_agent(d.pop("user_agent", UNSET))

        aperture_hook_metadata = cls(
            login_name=login_name,
            request_id=request_id,
            provider=provider,
            url=url,
            session_id=session_id,
            stable_node_id=stable_node_id,
            user_agent=user_agent,
        )

        aperture_hook_metadata.additional_properties = d
        return aperture_hook_metadata

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
