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

T = TypeVar("T", bound="ApertureLog")


@_attrs_define
class ApertureLog:
    """A single aperture log on s3.

    Attributes:
        format_ (Literal['aperture-log']):
        bucket (str):
        key (str):
    """

    format_: Literal["aperture-log"]
    bucket: str
    key: str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        format_ = self.format_

        bucket = self.bucket

        key = self.key

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "format": format_,
                "bucket": bucket,
                "key": key,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        format_ = cast(Literal["aperture-log"], d.pop("format"))
        if format_ != "aperture-log":
            raise ValueError(f"format must match const 'aperture-log', got '{format_}'")

        bucket = d.pop("bucket")

        key = d.pop("key")

        aperture_log = cls(
            format_=format_,
            bucket=bucket,
            key=key,
        )

        aperture_log.additional_properties = d
        return aperture_log

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
