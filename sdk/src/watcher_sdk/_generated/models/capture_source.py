from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Self, TypeVar, cast

from attrs import define as _attrs_define

from ..models.capture_source_type import CaptureSourceType
from ..types import UNSET, Unset

T = TypeVar("T", bound="CaptureSource")


@_attrs_define
class CaptureSource:
    """An integration that delivered a conversation, independent of its identity.

    ``name`` is an optional stable integration identifier, not a hostname, user,
    model or credential. An unnamed source preserves a known delivery category
    when historical data cannot establish the particular integration.

        Attributes:
            type_ (CaptureSourceType):
            name (None | str | Unset):
    """

    type_: CaptureSourceType
    name: None | str | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        type_ = self.type_.value

        name: None | str | Unset
        if isinstance(self.name, Unset):
            name = UNSET
        else:
            name = self.name

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "type": type_,
            }
        )
        if name is not UNSET:
            field_dict["name"] = name

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        d = dict(src_dict)
        type_ = CaptureSourceType(d.pop("type"))

        def _parse_name(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        name = _parse_name(d.pop("name", UNSET))

        capture_source = cls(
            type_=type_,
            name=name,
        )

        return capture_source
