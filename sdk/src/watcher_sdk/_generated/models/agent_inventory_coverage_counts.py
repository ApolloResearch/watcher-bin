from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Self, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="AgentInventoryCoverageCounts")


@_attrs_define
class AgentInventoryCoverageCounts:
    """People who used an agent in the last 7 days, by coverage.

    Attributes:
        monitored (int): Watcher received a session from them for this agent in the last 7 days.
        gap (int): Watcher received no session from them for this agent in the last 7 days.
        not_supported (int): Watcher cannot monitor this agent.
    """

    monitored: int
    gap: int
    not_supported: int
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        monitored = self.monitored

        gap = self.gap

        not_supported = self.not_supported

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "monitored": monitored,
                "gap": gap,
                "not_supported": not_supported,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        d = dict(src_dict)
        monitored = d.pop("monitored")

        gap = d.pop("gap")

        not_supported = d.pop("not_supported")

        agent_inventory_coverage_counts = cls(
            monitored=monitored,
            gap=gap,
            not_supported=not_supported,
        )

        agent_inventory_coverage_counts.additional_properties = d
        return agent_inventory_coverage_counts

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
