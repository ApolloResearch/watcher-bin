from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from typing_extensions import Self

from ..types import UNSET, Unset

T = TypeVar("T", bound="HookCallError")


@_attrs_define
class HookCallError:
    """A refused input inside a batch; other inputs still receive their own outcomes.

    Treat this as the corresponding scalar HTTP error, never as permission to
    execute the tool. It carries no judgment and creates no decision record.

        Attributes:
            status_code (int):
            detail (str):
            tool_use_id (None | str | Unset): Echoes this input's tool_use_id, or null when omitted.
    """

    status_code: int
    detail: str
    tool_use_id: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        status_code = self.status_code

        detail = self.detail

        tool_use_id: None | str | Unset
        if isinstance(self.tool_use_id, Unset):
            tool_use_id = UNSET
        else:
            tool_use_id = self.tool_use_id

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "status_code": status_code,
                "detail": detail,
            }
        )
        if tool_use_id is not UNSET:
            field_dict["tool_use_id"] = tool_use_id

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        d = dict(src_dict)
        status_code = d.pop("status_code")

        detail = d.pop("detail")

        def _parse_tool_use_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        tool_use_id = _parse_tool_use_id(d.pop("tool_use_id", UNSET))

        hook_call_error = cls(
            status_code=status_code,
            detail=detail,
            tool_use_id=tool_use_id,
        )

        hook_call_error.additional_properties = d
        return hook_call_error

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
