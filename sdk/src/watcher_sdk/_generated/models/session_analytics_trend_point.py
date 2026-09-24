from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from dateutil.parser import isoparse

T = TypeVar("T", bound="SessionAnalyticsTrendPoint")


@_attrs_define
class SessionAnalyticsTrendPoint:
    """Bucketed trend counts for aggregate charts.

    Both are daily-active session counts (distinct sessions with activity in the
    bucket), so ``matching_count`` reads directly as a slice of ``total_count``:
    those whose deep-review severity meets the requested threshold.

        Attributes:
            date (datetime.date):
            matching_count (int):
            total_count (int):
    """

    date: datetime.date
    matching_count: int
    total_count: int
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        date = self.date.isoformat()

        matching_count = self.matching_count

        total_count = self.total_count

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "date": date,
                "matching_count": matching_count,
                "total_count": total_count,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        date = isoparse(d.pop("date")).date()

        matching_count = d.pop("matching_count")

        total_count = d.pop("total_count")

        session_analytics_trend_point = cls(
            date=date,
            matching_count=matching_count,
            total_count=total_count,
        )

        session_analytics_trend_point.additional_properties = d
        return session_analytics_trend_point

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
