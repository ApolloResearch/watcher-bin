from __future__ import annotations

from collections.abc import Mapping
from typing import (
    TYPE_CHECKING,
    Any,
    Literal,
    TypeVar,
    cast,
)

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from typing_extensions import Self

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.content_data_data import ContentDataData


T = TypeVar("T", bound="ContentData")


@_attrs_define
class ContentData:
    """Model internal.

    Attributes:
        data (ContentDataData):
        internal (Any | None | Unset):
        type_ (Literal['data'] | Unset):  Default: 'data'.
    """

    data: ContentDataData
    internal: Any | None | Unset = UNSET
    type_: Literal["data"] | Unset = "data"
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = self.data.to_dict()

        internal: Any | None | Unset
        if isinstance(self.internal, Unset):
            internal = UNSET
        else:
            internal = self.internal

        type_ = self.type_

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "data": data,
            }
        )
        if internal is not UNSET:
            field_dict["internal"] = internal
        if type_ is not UNSET:
            field_dict["type"] = type_

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        from ..models.content_data_data import ContentDataData

        d = dict(src_dict)
        data = ContentDataData.from_dict(d.pop("data"))

        def _parse_internal(data: object) -> Any | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(Any | None | Unset, data)

        internal = _parse_internal(d.pop("internal", UNSET))

        type_ = cast(Literal["data"] | Unset, d.pop("type", UNSET))
        if type_ != "data" and not isinstance(type_, Unset):
            raise ValueError(f"type must match const 'data', got '{type_}'")

        content_data = cls(
            data=data,
            internal=internal,
            type_=type_,
        )

        content_data.additional_properties = d
        return content_data

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
