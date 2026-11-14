from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Self, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.aperture_selected_tool_call_params import (
        ApertureSelectedToolCallParams,
    )


T = TypeVar("T", bound="ApertureSelectedToolCall")


@_attrs_define
class ApertureSelectedToolCall:
    """One complete pending call supplied by Aperture's tool-call hook.

    ``id`` is absent for Gemini calls, which carry no native ID; those are
    matched to the response by position (see ``translate_aperture_pre_response``).

        Attributes:
            name (str):
            params (ApertureSelectedToolCallParams):
            id (None | str | Unset):
    """

    name: str
    params: ApertureSelectedToolCallParams
    id: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        name = self.name

        params = self.params.to_dict()

        id: None | str | Unset
        if isinstance(self.id, Unset):
            id = UNSET
        else:
            id = self.id

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "name": name,
                "params": params,
            }
        )
        if id is not UNSET:
            field_dict["id"] = id

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        from ..models.aperture_selected_tool_call_params import (
            ApertureSelectedToolCallParams,
        )

        d = dict(src_dict)
        name = d.pop("name")

        params = ApertureSelectedToolCallParams.from_dict(d.pop("params"))

        def _parse_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        id = _parse_id(d.pop("id", UNSET))

        aperture_selected_tool_call = cls(
            name=name,
            params=params,
            id=id,
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
