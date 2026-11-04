from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Self, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.aperture_pre_request_response_action import (
    AperturePreRequestResponseAction,
)
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.aperture_pre_request_response_request_body_type_0 import (
        AperturePreRequestResponseRequestBodyType0,
    )


T = TypeVar("T", bound="AperturePreRequestResponse")


@_attrs_define
class AperturePreRequestResponse:
    """Allow unchanged requests or replace the entire body with the notice added.

    Attributes:
        action (AperturePreRequestResponseAction):
        request_body (AperturePreRequestResponseRequestBodyType0 | None | Unset):
    """

    action: AperturePreRequestResponseAction
    request_body: AperturePreRequestResponseRequestBodyType0 | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.aperture_pre_request_response_request_body_type_0 import (
            AperturePreRequestResponseRequestBodyType0,
        )

        action = self.action.value

        request_body: dict[str, Any] | None | Unset
        if isinstance(self.request_body, Unset):
            request_body = UNSET
        elif isinstance(self.request_body, AperturePreRequestResponseRequestBodyType0):
            request_body = self.request_body.to_dict()
        else:
            request_body = self.request_body

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "action": action,
            }
        )
        if request_body is not UNSET:
            field_dict["request_body"] = request_body

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        from ..models.aperture_pre_request_response_request_body_type_0 import (
            AperturePreRequestResponseRequestBodyType0,
        )

        d = dict(src_dict)
        action = AperturePreRequestResponseAction(d.pop("action"))

        def _parse_request_body(
            data: object,
        ) -> AperturePreRequestResponseRequestBodyType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                request_body_type_0 = (
                    AperturePreRequestResponseRequestBodyType0.from_dict(data)
                )

                return request_body_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(AperturePreRequestResponseRequestBodyType0 | None | Unset, data)

        request_body = _parse_request_body(d.pop("request_body", UNSET))

        aperture_pre_request_response = cls(
            action=action,
            request_body=request_body,
        )

        aperture_pre_request_response.additional_properties = d
        return aperture_pre_request_response

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
