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

from ..models.content_audio_format import ContentAudioFormat
from ..types import UNSET, Unset

T = TypeVar("T", bound="ContentAudio")


@_attrs_define
class ContentAudio:
    """Audio content.

    Attributes:
        audio (str):
        format_ (ContentAudioFormat):
        internal (Any | None | Unset):
        type_ (Literal['audio'] | Unset):  Default: 'audio'.
    """

    audio: str
    format_: ContentAudioFormat
    internal: Any | None | Unset = UNSET
    type_: Literal["audio"] | Unset = "audio"
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        audio = self.audio

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
                "audio": audio,
                "format": format_,
            }
        )
        if internal is not UNSET:
            field_dict["internal"] = internal
        if type_ is not UNSET:
            field_dict["type"] = type_

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        d = dict(src_dict)
        audio = d.pop("audio")

        format_ = ContentAudioFormat(d.pop("format"))

        def _parse_internal(data: object) -> Any | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(Any | None | Unset, data)

        internal = _parse_internal(d.pop("internal", UNSET))

        type_ = cast(Literal["audio"] | Unset, d.pop("type", UNSET))
        if type_ != "audio" and not isinstance(type_, Unset):
            raise ValueError(f"type must match const 'audio', got '{type_}'")

        content_audio = cls(
            audio=audio,
            format_=format_,
            internal=internal,
            type_=type_,
        )

        content_audio.additional_properties = d
        return content_audio

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
