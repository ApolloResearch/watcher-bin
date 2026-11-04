from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Self, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.aperture_tool_modification_params import (
        ApertureToolModificationParams,
    )


T = TypeVar("T", bound="ApertureToolModification")


@_attrs_define
class ApertureToolModification:
    """Argument replacement for an existing native call; its tool and ID stay fixed.

    Attributes:
        id (str):
        params (ApertureToolModificationParams):
    """

    id: str
    params: ApertureToolModificationParams
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        id = self.id

        params = self.params.to_dict()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "id": id,
                "params": params,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        from ..models.aperture_tool_modification_params import (
            ApertureToolModificationParams,
        )

        d = dict(src_dict)
        id = d.pop("id")

        params = ApertureToolModificationParams.from_dict(d.pop("params"))

        aperture_tool_modification = cls(
            id=id,
            params=params,
        )

        aperture_tool_modification.additional_properties = d
        return aperture_tool_modification

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
