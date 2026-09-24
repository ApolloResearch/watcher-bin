from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from dateutil.parser import isoparse

T = TypeVar("T", bound="GradingUsageCostBucket")


@_attrs_define
class GradingUsageCostBucket:
    """Estimated grading spend (USD) for one time bucket, split by request kind.

    Costs are estimated from per-model token rates; usage on models without
    configured rates is excluded (see ``GradingUsageResponse.unpriced_models``).
    Only present when the deployment exposes token details.

        Attributes:
            date (datetime.date):
            trailing_cost (float):
            triage_cost (float):
            gateway_cost (float):
    """

    date: datetime.date
    trailing_cost: float
    triage_cost: float
    gateway_cost: float
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        date = self.date.isoformat()

        trailing_cost = self.trailing_cost

        triage_cost = self.triage_cost

        gateway_cost = self.gateway_cost

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "date": date,
                "trailing_cost": trailing_cost,
                "triage_cost": triage_cost,
                "gateway_cost": gateway_cost,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        date = isoparse(d.pop("date")).date()

        trailing_cost = d.pop("trailing_cost")

        triage_cost = d.pop("triage_cost")

        gateway_cost = d.pop("gateway_cost")

        grading_usage_cost_bucket = cls(
            date=date,
            trailing_cost=trailing_cost,
            triage_cost=triage_cost,
            gateway_cost=gateway_cost,
        )

        grading_usage_cost_bucket.additional_properties = d
        return grading_usage_cost_bucket

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
