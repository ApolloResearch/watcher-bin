from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Self, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.agent_inventory_gateway_summary import AgentInventoryGatewaySummary
    from ..models.agent_inventory_summary_agent import AgentInventorySummaryAgent


T = TypeVar("T", bound="AgentInventorySummaryResponse")


@_attrs_define
class AgentInventorySummaryResponse:
    """Organization-wide agent inventory counts.

    Agents with `people_using` of 0 are installed but unused; agents with `machines` of 0 are used by people whose
    machines do not report them, seen through a gateway or in sessions Watcher received.

        Attributes:
            enabled (bool):
            machines (int): Machines that reported in the last 90 days.
            people (int): People who own those machines.
            people_seen (int): People seen in the last 7 days, as the owner of a reporting machine or through a gateway: the
                base for every share of people.
            people_reporting (int): People who own a machine that reported in the last 7 days.
            gap_people (int): People with a coverage gap for at least one agent. The machine list filtered by `coverage=gap`
                shows their machines.
            unsanctioned_people (int | None): People who used any agent named in the `unsanctioned` query parameter in the
                last 7 days, on a reporting machine or through a gateway; null when the parameter is absent.
            newest_report_at (datetime.datetime | None):
            recent_days (int): How many days count as recent.
            agents (list[AgentInventorySummaryAgent]):
            gateway (AgentInventoryGatewaySummary): Clients seen in traffic through gateways connected to Watcher in the
                last 7 days.
    """

    enabled: bool
    machines: int
    people: int
    people_seen: int
    people_reporting: int
    gap_people: int
    unsanctioned_people: int | None
    newest_report_at: datetime.datetime | None
    recent_days: int
    agents: list[AgentInventorySummaryAgent]
    gateway: AgentInventoryGatewaySummary
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        enabled = self.enabled

        machines = self.machines

        people = self.people

        people_seen = self.people_seen

        people_reporting = self.people_reporting

        gap_people = self.gap_people

        unsanctioned_people: int | None
        unsanctioned_people = self.unsanctioned_people

        newest_report_at: None | str
        if isinstance(self.newest_report_at, datetime.datetime):
            newest_report_at = self.newest_report_at.isoformat()
        else:
            newest_report_at = self.newest_report_at

        recent_days = self.recent_days

        agents = []
        for agents_item_data in self.agents:
            agents_item = agents_item_data.to_dict()
            agents.append(agents_item)

        gateway = self.gateway.to_dict()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "enabled": enabled,
                "machines": machines,
                "people": people,
                "people_seen": people_seen,
                "people_reporting": people_reporting,
                "gap_people": gap_people,
                "unsanctioned_people": unsanctioned_people,
                "newest_report_at": newest_report_at,
                "recent_days": recent_days,
                "agents": agents,
                "gateway": gateway,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        from ..models.agent_inventory_gateway_summary import (
            AgentInventoryGatewaySummary,
        )
        from ..models.agent_inventory_summary_agent import AgentInventorySummaryAgent

        d = dict(src_dict)
        enabled = d.pop("enabled")

        machines = d.pop("machines")

        people = d.pop("people")

        people_seen = d.pop("people_seen")

        people_reporting = d.pop("people_reporting")

        gap_people = d.pop("gap_people")

        def _parse_unsanctioned_people(data: object) -> int | None:
            if data is None:
                return data
            return cast(int | None, data)

        unsanctioned_people = _parse_unsanctioned_people(d.pop("unsanctioned_people"))

        def _parse_newest_report_at(data: object) -> datetime.datetime | None:
            if data is None:
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                newest_report_at_type_0 = datetime.datetime.fromisoformat(data)

                return newest_report_at_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None, data)

        newest_report_at = _parse_newest_report_at(d.pop("newest_report_at"))

        recent_days = d.pop("recent_days")

        agents = []
        _agents = d.pop("agents")
        for agents_item_data in _agents:
            agents_item = AgentInventorySummaryAgent.from_dict(agents_item_data)

            agents.append(agents_item)

        gateway = AgentInventoryGatewaySummary.from_dict(d.pop("gateway"))

        agent_inventory_summary_response = cls(
            enabled=enabled,
            machines=machines,
            people=people,
            people_seen=people_seen,
            people_reporting=people_reporting,
            gap_people=gap_people,
            unsanctioned_people=unsanctioned_people,
            newest_report_at=newest_report_at,
            recent_days=recent_days,
            agents=agents,
            gateway=gateway,
        )

        agent_inventory_summary_response.additional_properties = d
        return agent_inventory_summary_response

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
