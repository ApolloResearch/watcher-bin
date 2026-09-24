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

from ..models.content_video_format import ContentVideoFormat
from ..types import UNSET, Unset

T = TypeVar("T", bound="ContentVideo")


@_attrs_define
class ContentVideo:
    """Video content.

    Attributes:
        video (str):
        format_ (ContentVideoFormat):
        internal (Any | None | Unset):
        type_ (Literal['video'] | Unset):  Default: 'video'.
    """

    video: str
    format_: ContentVideoFormat
    internal: Any | None | Unset = UNSET
    type_: Literal["video"] | Unset = "video"
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        video = self.video

        format_ = self.format_.value

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
                "video": video,
                "format": format_,
            }
        )
        if internal is not UNSET:
            field_dict["internal"] = internal
        if type_ is not UNSET:
            field_dict["type"] = type_

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        video = d.pop("video")

        format_ = ContentVideoFormat(d.pop("format"))

        def _parse_internal(data: object) -> Any | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(Any | None | Unset, data)

        internal = _parse_internal(d.pop("internal", UNSET))

        type_ = cast(Literal["video"] | Unset, d.pop("type", UNSET))
        if type_ != "video" and not isinstance(type_, Unset):
            raise ValueError(f"type must match const 'video', got '{type_}'")

        content_video = cls(
            video=video,
            format_=format_,
            internal=internal,
            type_=type_,
        )

        content_video.additional_properties = d
        return content_video

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
