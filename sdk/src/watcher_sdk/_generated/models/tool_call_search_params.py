from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from typing_extensions import Self

from ..models.tool_call_search_params_sort_by import ToolCallSearchParamsSortBy
from ..models.tool_call_search_params_sort_order import ToolCallSearchParamsSortOrder
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.tool_call_search_filters import ToolCallSearchFilters


T = TypeVar("T", bound="ToolCallSearchParams")


@_attrs_define
class ToolCallSearchParams:
    """Request body for POST /tool-calls/search.

    Attributes:
        limit (int | Unset): Maximum rows to return. Default: 50.
        offset (int | Unset): Matching rows to skip. Default: 0.
        sort_by (ToolCallSearchParamsSortBy | Unset): Field used to order matching calls. Default:
            ToolCallSearchParamsSortBy.SEVERITY.
        sort_order (ToolCallSearchParamsSortOrder | Unset): Direction for the primary sort field. Default:
            ToolCallSearchParamsSortOrder.DESC.
        filters (ToolCallSearchFilters | Unset): Filter options for the tool-call list. Every field is optional and
            ANDed.
    """

    limit: int | Unset = 50
    offset: int | Unset = 0
    sort_by: ToolCallSearchParamsSortBy | Unset = ToolCallSearchParamsSortBy.SEVERITY
    sort_order: ToolCallSearchParamsSortOrder | Unset = (
        ToolCallSearchParamsSortOrder.DESC
    )
    filters: ToolCallSearchFilters | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        limit = self.limit

        offset = self.offset

        sort_by: str | Unset = UNSET
        if not isinstance(self.sort_by, Unset):
            sort_by = self.sort_by.value

        sort_order: str | Unset = UNSET
        if not isinstance(self.sort_order, Unset):
            sort_order = self.sort_order.value

        filters: dict[str, Any] | Unset = UNSET
        if not isinstance(self.filters, Unset):
            filters = self.filters.to_dict()

        field_dict: dict[str, Any] = {}

        field_dict.update({})
        if limit is not UNSET:
            field_dict["limit"] = limit
        if offset is not UNSET:
            field_dict["offset"] = offset
        if sort_by is not UNSET:
            field_dict["sort_by"] = sort_by
        if sort_order is not UNSET:
            field_dict["sort_order"] = sort_order
        if filters is not UNSET:
            field_dict["filters"] = filters

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        from ..models.tool_call_search_filters import (
            ToolCallSearchFilters,
        )

        d = dict(src_dict)
        limit = d.pop("limit", UNSET)

        offset = d.pop("offset", UNSET)

        _sort_by = d.pop("sort_by", UNSET)
        sort_by: ToolCallSearchParamsSortBy | Unset
        if isinstance(_sort_by, Unset):
            sort_by = UNSET
        else:
            sort_by = ToolCallSearchParamsSortBy(_sort_by)

        _sort_order = d.pop("sort_order", UNSET)
        sort_order: ToolCallSearchParamsSortOrder | Unset
        if isinstance(_sort_order, Unset):
            sort_order = UNSET
        else:
            sort_order = ToolCallSearchParamsSortOrder(_sort_order)

        _filters = d.pop("filters", UNSET)
        filters: ToolCallSearchFilters | Unset
        if isinstance(_filters, Unset):
            filters = UNSET
        else:
            filters = ToolCallSearchFilters.from_dict(_filters)

        tool_call_search_params = cls(
            limit=limit,
            offset=offset,
            sort_by=sort_by,
            sort_order=sort_order,
            filters=filters,
        )

        return tool_call_search_params
