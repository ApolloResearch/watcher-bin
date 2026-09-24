from __future__ import annotations

from collections.abc import Mapping
from typing import (
    Any,
    Literal,
    TypeVar,
    cast,
)

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.content_image_detail import ContentImageDetail
from ..types import UNSET, Unset

T = TypeVar("T", bound="ContentImage")


@_attrs_define
class ContentImage:
    """Image content.

    Attributes:
        image (str):
        internal (Any | None | Unset):
        type_ (Literal['image'] | Unset):  Default: 'image'.
        detail (ContentImageDetail | Unset):  Default: ContentImageDetail.AUTO.
    """

    image: str
    internal: Any | None | Unset = UNSET
    type_: Literal["image"] | Unset = "image"
    detail: ContentImageDetail | Unset = ContentImageDetail.AUTO
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        image = self.image

        internal: Any | None | Unset
        if isinstance(self.internal, Unset):
            internal = UNSET
        else:
            internal = self.internal

        type_ = self.type_

        detail: str | Unset = UNSET
        if not isinstance(self.detail, Unset):
            detail = self.detail.value

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "image": image,
            }
        )
        if internal is not UNSET:
            field_dict["internal"] = internal
        if type_ is not UNSET:
            field_dict["type"] = type_
        if detail is not UNSET:
            field_dict["detail"] = detail

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        image = d.pop("image")

        def _parse_internal(data: object) -> Any | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(Any | None | Unset, data)

        internal = _parse_internal(d.pop("internal", UNSET))

        type_ = cast(Literal["image"] | Unset, d.pop("type", UNSET))
        if type_ != "image" and not isinstance(type_, Unset):
            raise ValueError(f"type must match const 'image', got '{type_}'")

        _detail = d.pop("detail", UNSET)
        detail: ContentImageDetail | Unset
        if isinstance(_detail, Unset):
            detail = UNSET
        else:
            detail = ContentImageDetail(_detail)

        content_image = cls(
            image=image,
            internal=internal,
            type_=type_,
            detail=detail,
        )

        content_image.additional_properties = d
        return content_image

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
