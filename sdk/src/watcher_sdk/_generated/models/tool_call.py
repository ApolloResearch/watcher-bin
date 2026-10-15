from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from typing_extensions import Self

from ..models.tool_call_type import ToolCallType
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.tool_call_arguments import ToolCallArguments
    from ..models.tool_call_content import ToolCallContent


T = TypeVar("T", bound="ToolCall")


@_attrs_define
class ToolCall:
    """
    Attributes:
        id (str):
        function (str):
        arguments (ToolCallArguments):
        parse_error (None | str | Unset):
        view (None | ToolCallContent | Unset):
        type_ (ToolCallType | Unset):  Default: ToolCallType.FUNCTION.
    """

    id: str
    function: str
    arguments: ToolCallArguments
    parse_error: None | str | Unset = UNSET
    view: None | ToolCallContent | Unset = UNSET
    type_: ToolCallType | Unset = ToolCallType.FUNCTION
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.tool_call_content import ToolCallContent

        id = self.id

        function = self.function

        arguments = self.arguments.to_dict()

        parse_error: None | str | Unset
        if isinstance(self.parse_error, Unset):
            parse_error = UNSET
        else:
            parse_error = self.parse_error

        view: dict[str, Any] | None | Unset
        if isinstance(self.view, Unset):
            view = UNSET
        elif isinstance(self.view, ToolCallContent):
            view = self.view.to_dict()
        else:
            view = self.view

        type_: str | Unset = UNSET
        if not isinstance(self.type_, Unset):
            type_ = self.type_.value

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "id": id,
                "function": function,
                "arguments": arguments,
            }
        )
        if parse_error is not UNSET:
            field_dict["parse_error"] = parse_error
        if view is not UNSET:
            field_dict["view"] = view
        if type_ is not UNSET:
            field_dict["type"] = type_

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        from ..models.tool_call_arguments import ToolCallArguments
        from ..models.tool_call_content import ToolCallContent

        d = dict(src_dict)
        id = d.pop("id")

        function = d.pop("function")

        arguments = ToolCallArguments.from_dict(d.pop("arguments"))

        def _parse_parse_error(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        parse_error = _parse_parse_error(d.pop("parse_error", UNSET))

        def _parse_view(data: object) -> None | ToolCallContent | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                view_type_0 = ToolCallContent.from_dict(data)

                return view_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | ToolCallContent | Unset, data)

        view = _parse_view(d.pop("view", UNSET))

        _type_ = d.pop("type", UNSET)
        type_: ToolCallType | Unset
        if isinstance(_type_, Unset):
            type_ = UNSET
        else:
            type_ = ToolCallType(_type_)

        tool_call = cls(
            id=id,
            function=function,
            arguments=arguments,
            parse_error=parse_error,
            view=view,
            type_=type_,
        )

        tool_call.additional_properties = d
        return tool_call

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
