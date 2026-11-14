from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Self, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.aperture_tool_modification_params_type_0 import (
        ApertureToolModificationParamsType0,
    )


T = TypeVar("T", bound="ApertureToolModification")


@_attrs_define
class ApertureToolModification:
    """Aperture's edit of one pending native call, which keeps its ID; other calls are released unchanged.

    ``params`` replaces the call's arguments. ``name`` also renames the call to
    another tool the client declared in the request. ``remove`` drops the call
    from the response instead; when no call is left, Aperture ends the response
    as a text answer, so the client waits for no tool result.

        Attributes:
            id (str):
            name (None | str | Unset):
            params (ApertureToolModificationParamsType0 | None | Unset):
            remove (bool | None | Unset):
    """

    id: str
    name: None | str | Unset = UNSET
    params: ApertureToolModificationParamsType0 | None | Unset = UNSET
    remove: bool | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.aperture_tool_modification_params_type_0 import (
            ApertureToolModificationParamsType0,
        )

        id = self.id

        name: None | str | Unset
        if isinstance(self.name, Unset):
            name = UNSET
        else:
            name = self.name

        params: dict[str, Any] | None | Unset
        if isinstance(self.params, Unset):
            params = UNSET
        elif isinstance(self.params, ApertureToolModificationParamsType0):
            params = self.params.to_dict()
        else:
            params = self.params

        remove: bool | None | Unset
        if isinstance(self.remove, Unset):
            remove = UNSET
        else:
            remove = self.remove

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "id": id,
            }
        )
        if name is not UNSET:
            field_dict["name"] = name
        if params is not UNSET:
            field_dict["params"] = params
        if remove is not UNSET:
            field_dict["remove"] = remove

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        from ..models.aperture_tool_modification_params_type_0 import (
            ApertureToolModificationParamsType0,
        )

        d = dict(src_dict)
        id = d.pop("id")

        def _parse_name(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        name = _parse_name(d.pop("name", UNSET))

        def _parse_params(
            data: object,
        ) -> ApertureToolModificationParamsType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                params_type_0 = ApertureToolModificationParamsType0.from_dict(data)

                return params_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(ApertureToolModificationParamsType0 | None | Unset, data)

        params = _parse_params(d.pop("params", UNSET))

        def _parse_remove(data: object) -> bool | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(bool | None | Unset, data)

        remove = _parse_remove(d.pop("remove", UNSET))

        aperture_tool_modification = cls(
            id=id,
            name=name,
            params=params,
            remove=remove,
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
