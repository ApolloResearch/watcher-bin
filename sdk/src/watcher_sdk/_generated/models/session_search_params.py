from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.session_search_params_sort_by import SessionSearchParamsSortBy
from ..models.session_search_params_sort_order import SessionSearchParamsSortOrder
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.session_search_filters import SessionSearchFilters


T = TypeVar("T", bound="SessionSearchParams")


@_attrs_define
class SessionSearchParams:
    """Request body for POST /sessions/search.

    Supports all filtering, pagination, and sort options.

        Attributes:
            limit (int | Unset):  Default: 100.
            offset (int | Unset):  Default: 0.
            sort_by (SessionSearchParamsSortBy | Unset):  Default: SessionSearchParamsSortBy.ENDED_AT.
            sort_order (SessionSearchParamsSortOrder | Unset):  Default: SessionSearchParamsSortOrder.DESC.
            filters (None | SessionSearchFilters | Unset):
    """

    limit: int | Unset = 100
    offset: int | Unset = 0
    sort_by: SessionSearchParamsSortBy | Unset = SessionSearchParamsSortBy.ENDED_AT
    sort_order: SessionSearchParamsSortOrder | Unset = SessionSearchParamsSortOrder.DESC
    filters: None | SessionSearchFilters | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.session_search_filters import SessionSearchFilters

        limit = self.limit

        offset = self.offset

        sort_by: str | Unset = UNSET
        if not isinstance(self.sort_by, Unset):
            sort_by = self.sort_by.value

        sort_order: str | Unset = UNSET
        if not isinstance(self.sort_order, Unset):
            sort_order = self.sort_order.value

        filters: dict[str, Any] | None | Unset
        if isinstance(self.filters, Unset):
            filters = UNSET
        elif isinstance(self.filters, SessionSearchFilters):
            filters = self.filters.to_dict()
        else:
            filters = self.filters

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
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
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.session_search_filters import SessionSearchFilters

        d = dict(src_dict)
        limit = d.pop("limit", UNSET)

        offset = d.pop("offset", UNSET)

        _sort_by = d.pop("sort_by", UNSET)
        sort_by: SessionSearchParamsSortBy | Unset
        if isinstance(_sort_by, Unset):
            sort_by = UNSET
        else:
            sort_by = SessionSearchParamsSortBy(_sort_by)

        _sort_order = d.pop("sort_order", UNSET)
        sort_order: SessionSearchParamsSortOrder | Unset
        if isinstance(_sort_order, Unset):
            sort_order = UNSET
        else:
            sort_order = SessionSearchParamsSortOrder(_sort_order)

        def _parse_filters(data: object) -> None | SessionSearchFilters | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                filters_type_0 = SessionSearchFilters.from_dict(data)

                return filters_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | SessionSearchFilters | Unset, data)

        filters = _parse_filters(d.pop("filters", UNSET))

        session_search_params = cls(
            limit=limit,
            offset=offset,
            sort_by=sort_by,
            sort_order=sort_order,
            filters=filters,
        )

        session_search_params.additional_properties = d
        return session_search_params

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
