from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Self, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.aperture_hook_metadata import ApertureHookMetadata
    from ..models.aperture_pre_request_request_body import AperturePreRequestRequestBody


T = TypeVar("T", bound="AperturePreRequest")


@_attrs_define
class AperturePreRequest:
    """Aperture's original provider request before inference.

    Attributes:
        metadata (ApertureHookMetadata): Tailscale Aperture-owned identity fields; unknown additions are accepted.

            ``request_id`` identifies a capture, never a conversation. ``session_id``
            is Aperture's own session id: one it took from the client (prefix
            ``xsid_`` or ``pisn_``) is recorded as the conversation id of a capture
            without a native one, and any other value is ignored. The provider key
            and URL describe routing and do not identify the developer's harness.
            ``user_agent`` supplies application evidence to the format parser. The
            parser applies the supported harness's marker and system-identity rules;
            selecting a wire format alone never admits an application. These fields
            classify captured traffic; they do not authenticate the caller.
        request_body (AperturePreRequestRequestBody):
    """

    metadata: ApertureHookMetadata
    request_body: AperturePreRequestRequestBody
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        metadata = self.metadata.to_dict()

        request_body = self.request_body.to_dict()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "metadata": metadata,
                "request_body": request_body,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        from ..models.aperture_hook_metadata import ApertureHookMetadata
        from ..models.aperture_pre_request_request_body import (
            AperturePreRequestRequestBody,
        )

        d = dict(src_dict)
        metadata = ApertureHookMetadata.from_dict(d.pop("metadata"))

        request_body = AperturePreRequestRequestBody.from_dict(d.pop("request_body"))

        aperture_pre_request = cls(
            metadata=metadata,
            request_body=request_body,
        )

        aperture_pre_request.additional_properties = d
        return aperture_pre_request

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
