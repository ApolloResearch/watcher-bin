from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from typing_extensions import Self

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.aperture_hook_metadata import ApertureHookMetadata
    from ..models.aperture_hook_request_request_body import (
        ApertureHookRequestRequestBody,
    )
    from ..models.aperture_hook_request_response_body_type_0 import (
        ApertureHookRequestResponseBodyType0,
    )


T = TypeVar("T", bound="ApertureHookRequest")


@_attrs_define
class ApertureHookRequest:
    """The fixed webhook envelope with both required send types enabled.

    Raw request and reconstructed response objects are forwarded to the selected
    format parser. A null or absent response represents an upstream call that
    produced no response body and is skipped: Aperture omits ``response_body``
    when the client disconnects before the provider answers (capture status 0).
    Extra metadata and send types are ignored.

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
            request_body (ApertureHookRequestRequestBody):
            response_body (ApertureHookRequestResponseBodyType0 | None | Unset):
    """

    metadata: ApertureHookMetadata
    request_body: ApertureHookRequestRequestBody
    response_body: ApertureHookRequestResponseBodyType0 | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.aperture_hook_request_response_body_type_0 import (
            ApertureHookRequestResponseBodyType0,
        )

        metadata = self.metadata.to_dict()

        request_body = self.request_body.to_dict()

        response_body: dict[str, Any] | None | Unset
        if isinstance(self.response_body, Unset):
            response_body = UNSET
        elif isinstance(self.response_body, ApertureHookRequestResponseBodyType0):
            response_body = self.response_body.to_dict()
        else:
            response_body = self.response_body

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "metadata": metadata,
                "request_body": request_body,
            }
        )
        if response_body is not UNSET:
            field_dict["response_body"] = response_body

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        from ..models.aperture_hook_metadata import (
            ApertureHookMetadata,
        )
        from ..models.aperture_hook_request_request_body import (
            ApertureHookRequestRequestBody,
        )
        from ..models.aperture_hook_request_response_body_type_0 import (
            ApertureHookRequestResponseBodyType0,
        )

        d = dict(src_dict)
        metadata = ApertureHookMetadata.from_dict(d.pop("metadata"))

        request_body = ApertureHookRequestRequestBody.from_dict(d.pop("request_body"))

        def _parse_response_body(
            data: object,
        ) -> ApertureHookRequestResponseBodyType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                response_body_type_0 = ApertureHookRequestResponseBodyType0.from_dict(
                    data
                )

                return response_body_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(ApertureHookRequestResponseBodyType0 | None | Unset, data)

        response_body = _parse_response_body(d.pop("response_body", UNSET))

        aperture_hook_request = cls(
            metadata=metadata,
            request_body=request_body,
            response_body=response_body,
        )

        aperture_hook_request.additional_properties = d
        return aperture_hook_request

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
