from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Self, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.aperture_hook_metadata import ApertureHookMetadata
    from ..models.aperture_pre_response_request_request_body import (
        AperturePreResponseRequestRequestBody,
    )
    from ..models.aperture_pre_response_request_response_body import (
        AperturePreResponseRequestResponseBody,
    )
    from ..models.aperture_response_window import ApertureResponseWindow
    from ..models.aperture_selected_tool_call import ApertureSelectedToolCall


T = TypeVar("T", bound="AperturePreResponseRequest")


@_attrs_define
class AperturePreResponseRequest:
    """Blocking callback with original context and the exact calls awaiting release.

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
        request_body (AperturePreResponseRequestRequestBody):
        response_body (AperturePreResponseRequestResponseBody):
        tool_calls (list[ApertureSelectedToolCall] | None | Unset):
        response_window (ApertureResponseWindow | None | Unset):
    """

    metadata: ApertureHookMetadata
    request_body: AperturePreResponseRequestRequestBody
    response_body: AperturePreResponseRequestResponseBody
    tool_calls: list[ApertureSelectedToolCall] | None | Unset = UNSET
    response_window: ApertureResponseWindow | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.aperture_response_window import ApertureResponseWindow

        metadata = self.metadata.to_dict()

        request_body = self.request_body.to_dict()

        response_body = self.response_body.to_dict()

        tool_calls: list[dict[str, Any]] | None | Unset
        if isinstance(self.tool_calls, Unset):
            tool_calls = UNSET
        elif isinstance(self.tool_calls, list):
            tool_calls = []
            for tool_calls_type_0_item_data in self.tool_calls:
                tool_calls_type_0_item = tool_calls_type_0_item_data.to_dict()
                tool_calls.append(tool_calls_type_0_item)

        else:
            tool_calls = self.tool_calls

        response_window: dict[str, Any] | None | Unset
        if isinstance(self.response_window, Unset):
            response_window = UNSET
        elif isinstance(self.response_window, ApertureResponseWindow):
            response_window = self.response_window.to_dict()
        else:
            response_window = self.response_window

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "metadata": metadata,
                "request_body": request_body,
                "response_body": response_body,
            }
        )
        if tool_calls is not UNSET:
            field_dict["tool_calls"] = tool_calls
        if response_window is not UNSET:
            field_dict["response_window"] = response_window

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        from ..models.aperture_hook_metadata import ApertureHookMetadata
        from ..models.aperture_pre_response_request_request_body import (
            AperturePreResponseRequestRequestBody,
        )
        from ..models.aperture_pre_response_request_response_body import (
            AperturePreResponseRequestResponseBody,
        )
        from ..models.aperture_response_window import ApertureResponseWindow
        from ..models.aperture_selected_tool_call import ApertureSelectedToolCall

        d = dict(src_dict)
        metadata = ApertureHookMetadata.from_dict(d.pop("metadata"))

        request_body = AperturePreResponseRequestRequestBody.from_dict(
            d.pop("request_body")
        )

        response_body = AperturePreResponseRequestResponseBody.from_dict(
            d.pop("response_body")
        )

        def _parse_tool_calls(
            data: object,
        ) -> list[ApertureSelectedToolCall] | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                tool_calls_type_0 = []
                _tool_calls_type_0 = data
                for tool_calls_type_0_item_data in _tool_calls_type_0:
                    tool_calls_type_0_item = ApertureSelectedToolCall.from_dict(
                        tool_calls_type_0_item_data
                    )

                    tool_calls_type_0.append(tool_calls_type_0_item)

                return tool_calls_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(list[ApertureSelectedToolCall] | None | Unset, data)

        tool_calls = _parse_tool_calls(d.pop("tool_calls", UNSET))

        def _parse_response_window(
            data: object,
        ) -> ApertureResponseWindow | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                response_window_type_0 = ApertureResponseWindow.from_dict(data)

                return response_window_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(ApertureResponseWindow | None | Unset, data)

        response_window = _parse_response_window(d.pop("response_window", UNSET))

        aperture_pre_response_request = cls(
            metadata=metadata,
            request_body=request_body,
            response_body=response_body,
            tool_calls=tool_calls,
            response_window=response_window,
        )

        aperture_pre_response_request.additional_properties = d
        return aperture_pre_response_request

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
