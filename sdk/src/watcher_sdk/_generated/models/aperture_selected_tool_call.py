from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Self, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.aperture_selected_tool_call_params import (
        ApertureSelectedToolCallParams,
    )


T = TypeVar("T", bound="ApertureSelectedToolCall")


@_attrs_define
class ApertureSelectedToolCall:
    """One complete pending call supplied by Aperture's tool-call hook.

    Attributes:
        id (str):
        name (str):
        params (ApertureSelectedToolCallParams):
    """

    id: str
    name: str
    params: ApertureSelectedToolCallParams
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        id = self.id

        name = self.name

        params = self.params.to_dict()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "id": id,
                "name": name,
                "params": params,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        from ..models.aperture_selected_tool_call_params import (
            ApertureSelectedToolCallParams,
        )

        d = dict(src_dict)
        id = d.pop("id")

        name = d.pop("name")

        params = ApertureSelectedToolCallParams.from_dict(d.pop("params"))

        aperture_selected_tool_call = cls(
            id=id,
            name=name,
            params=params,
        )

        aperture_selected_tool_call.additional_properties = d
        return aperture_selected_tool_call

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
