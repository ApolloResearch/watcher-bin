from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.document_range_type import DocumentRangeType

T = TypeVar("T", bound="DocumentRange")


@_attrs_define
class DocumentRange:
    """A range specifying a section of a document.

    Attributes:
        type_ (DocumentRangeType):
        start_index (int):
        end_index (int):
    """

    type_: DocumentRangeType
    start_index: int
    end_index: int
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        type_ = self.type_.value

        start_index = self.start_index

        end_index = self.end_index

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "type": type_,
                "start_index": start_index,
                "end_index": end_index,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        type_ = DocumentRangeType(d.pop("type"))

        start_index = d.pop("start_index")

        end_index = d.pop("end_index")

        document_range = cls(
            type_=type_,
            start_index=start_index,
            end_index=end_index,
        )

        document_range.additional_properties = d
        return document_range

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
