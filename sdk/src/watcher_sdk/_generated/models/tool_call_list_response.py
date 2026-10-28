from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Self, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.available_tool_call_list_item import AvailableToolCallListItem
    from ..models.scrubbed_tool_call_list_item import ScrubbedToolCallListItem


T = TypeVar("T", bound="ToolCallListResponse")


@_attrs_define
class ToolCallListResponse:
    """Paginated response from POST /v1/tool-calls/search.

    Attributes:
        tool_calls (list[AvailableToolCallListItem | ScrubbedToolCallListItem]):
        total (int):
        limit (int):
        offset (int):
    """

    tool_calls: list[AvailableToolCallListItem | ScrubbedToolCallListItem]
    total: int
    limit: int
    offset: int
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.available_tool_call_list_item import AvailableToolCallListItem

        tool_calls = []
        for tool_calls_item_data in self.tool_calls:
            tool_calls_item: dict[str, Any]
            if isinstance(tool_calls_item_data, AvailableToolCallListItem):
                tool_calls_item = tool_calls_item_data.to_dict()
            else:
                tool_calls_item = tool_calls_item_data.to_dict()

            tool_calls.append(tool_calls_item)

        total = self.total

        limit = self.limit

        offset = self.offset

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "tool_calls": tool_calls,
                "total": total,
                "limit": limit,
                "offset": offset,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        from ..models.available_tool_call_list_item import AvailableToolCallListItem
        from ..models.scrubbed_tool_call_list_item import ScrubbedToolCallListItem

        d = dict(src_dict)
        tool_calls = []
        _tool_calls = d.pop("tool_calls")
        for tool_calls_item_data in _tool_calls:

            def _parse_tool_calls_item(
                data: object,
            ) -> AvailableToolCallListItem | ScrubbedToolCallListItem:
                try:
                    if not isinstance(data, dict):
                        raise TypeError()
                    tool_calls_item_type_0 = AvailableToolCallListItem.from_dict(data)

                    return tool_calls_item_type_0
                except (TypeError, ValueError, AttributeError, KeyError):
                    pass
                if not isinstance(data, dict):
                    raise TypeError()
                tool_calls_item_type_1 = ScrubbedToolCallListItem.from_dict(data)

                return tool_calls_item_type_1

            tool_calls_item = _parse_tool_calls_item(tool_calls_item_data)

            tool_calls.append(tool_calls_item)

        total = d.pop("total")

        limit = d.pop("limit")

        offset = d.pop("offset")

        tool_call_list_response = cls(
            tool_calls=tool_calls,
            total=total,
            limit=limit,
            offset=offset,
        )

        tool_call_list_response.additional_properties = d
        return tool_call_list_response

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
