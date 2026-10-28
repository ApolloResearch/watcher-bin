from __future__ import annotations

from collections.abc import Mapping
from typing import (
    Any,
    Literal,
    Self,
    TypeVar,
    cast,
)

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="ApertureHookAccepted")


@_attrs_define
class ApertureHookAccepted:
    """Admission acknowledgement; processing finishes asynchronously and is not durable.

    Attributes:
        status (Literal['accepted'] | Unset):  Default: 'accepted'.
    """

    status: Literal["accepted"] | Unset = "accepted"
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        status = self.status

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if status is not UNSET:
            field_dict["status"] = status

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        d = dict(src_dict)
        status = cast(Literal["accepted"] | Unset, d.pop("status", UNSET))
        if status != "accepted" and not isinstance(status, Unset):
            raise ValueError(f"status must match const 'accepted', got '{status}'")

        aperture_hook_accepted = cls(
            status=status,
        )

        aperture_hook_accepted.additional_properties = d
        return aperture_hook_accepted

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
