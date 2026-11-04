from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Self, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.agent_inventory_coverage_counts import AgentInventoryCoverageCounts


T = TypeVar("T", bound="AgentInventorySummaryAgent")


@_attrs_define
class AgentInventorySummaryAgent:
    """Counts for one agent across your organization.

    Attributes:
        agent_id (str):
        supported (bool): Whether Watcher can monitor this agent.
        use_detected (bool): Whether the Watcher client can tell when this agent was last used. Without that, machines
            never report using it, so its coverage counts come only from sessions Watcher received.
        machines (int): Machines where the agent is installed.
        machines_recent (int): Machines where the agent was used in the last 7 days.
        coverage (AgentInventoryCoverageCounts): People who used an agent in the last 7 days, by coverage.
        gateway_people (int): People whose gateway traffic for this agent was seen in the last 7 days.
        watcher_people (int): People whose sessions for this agent reached Watcher in the last 7 days, by any route.
        people_using (int): People who used the agent in the last 7 days: on a reporting machine, in sessions Watcher
            received or through a gateway. Only people the user list shows are counted.
    """

    agent_id: str
    supported: bool
    use_detected: bool
    machines: int
    machines_recent: int
    coverage: AgentInventoryCoverageCounts
    gateway_people: int
    watcher_people: int
    people_using: int
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        agent_id = self.agent_id

        supported = self.supported

        use_detected = self.use_detected

        machines = self.machines

        machines_recent = self.machines_recent

        coverage = self.coverage.to_dict()

        gateway_people = self.gateway_people

        watcher_people = self.watcher_people

        people_using = self.people_using

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "agent_id": agent_id,
                "supported": supported,
                "use_detected": use_detected,
                "machines": machines,
                "machines_recent": machines_recent,
                "coverage": coverage,
                "gateway_people": gateway_people,
                "watcher_people": watcher_people,
                "people_using": people_using,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        from ..models.agent_inventory_coverage_counts import (
            AgentInventoryCoverageCounts,
        )

        d = dict(src_dict)
        agent_id = d.pop("agent_id")

        supported = d.pop("supported")

        use_detected = d.pop("use_detected")

        machines = d.pop("machines")

        machines_recent = d.pop("machines_recent")

        coverage = AgentInventoryCoverageCounts.from_dict(d.pop("coverage"))

        gateway_people = d.pop("gateway_people")

        watcher_people = d.pop("watcher_people")

        people_using = d.pop("people_using")

        agent_inventory_summary_agent = cls(
            agent_id=agent_id,
            supported=supported,
            use_detected=use_detected,
            machines=machines,
            machines_recent=machines_recent,
            coverage=coverage,
            gateway_people=gateway_people,
            watcher_people=watcher_people,
            people_using=people_using,
        )

        agent_inventory_summary_agent.additional_properties = d
        return agent_inventory_summary_agent

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
