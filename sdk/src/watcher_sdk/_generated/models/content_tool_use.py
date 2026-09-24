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

from ..models.content_tool_use_tool_type import ContentToolUseToolType
from ..types import UNSET, Unset

T = TypeVar("T", bound="ContentToolUse")


@_attrs_define
class ContentToolUse:
    """Server side tool use.

    Attributes:
        tool_type (ContentToolUseToolType):
        id (str):
        name (str):
        arguments (str):
        result (str):
        internal (Any | None | Unset):
        type_ (Literal['tool_use'] | Unset):  Default: 'tool_use'.
        context (None | str | Unset):
        error (None | str | Unset):
    """

    tool_type: ContentToolUseToolType
    id: str
    name: str
    arguments: str
    result: str
    internal: Any | None | Unset = UNSET
    type_: Literal["tool_use"] | Unset = "tool_use"
    context: None | str | Unset = UNSET
    error: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        tool_type = self.tool_type.value

        id = self.id

        name = self.name

        arguments = self.arguments

        result = self.result

        internal: Any | None | Unset
        if isinstance(self.internal, Unset):
            internal = UNSET
        else:
            internal = self.internal

        type_ = self.type_

        context: None | str | Unset
        if isinstance(self.context, Unset):
            context = UNSET
        else:
            context = self.context

        error: None | str | Unset
        if isinstance(self.error, Unset):
            error = UNSET
        else:
            error = self.error

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "tool_type": tool_type,
                "id": id,
                "name": name,
                "arguments": arguments,
                "result": result,
            }
        )
        if internal is not UNSET:
            field_dict["internal"] = internal
        if type_ is not UNSET:
            field_dict["type"] = type_
        if context is not UNSET:
            field_dict["context"] = context
        if error is not UNSET:
            field_dict["error"] = error

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        tool_type = ContentToolUseToolType(d.pop("tool_type"))

        id = d.pop("id")

        name = d.pop("name")

        arguments = d.pop("arguments")

        result = d.pop("result")

        def _parse_internal(data: object) -> Any | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(Any | None | Unset, data)

        internal = _parse_internal(d.pop("internal", UNSET))

        type_ = cast(Literal["tool_use"] | Unset, d.pop("type", UNSET))
        if type_ != "tool_use" and not isinstance(type_, Unset):
            raise ValueError(f"type must match const 'tool_use', got '{type_}'")

        def _parse_context(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        context = _parse_context(d.pop("context", UNSET))

        def _parse_error(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        error = _parse_error(d.pop("error", UNSET))

        content_tool_use = cls(
            tool_type=tool_type,
            id=id,
            name=name,
            arguments=arguments,
            result=result,
            internal=internal,
            type_=type_,
            context=context,
            error=error,
        )

        content_tool_use.additional_properties = d
        return content_tool_use

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
