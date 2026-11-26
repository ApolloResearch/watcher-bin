from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Self, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.agent_inventory_health_agent import AgentInventoryHealthAgent
    from ..models.agent_inventory_health_delivery import AgentInventoryHealthDelivery
    from ..models.agent_inventory_health_self_check_type_0 import (
        AgentInventoryHealthSelfCheckType0,
    )
    from ..models.agent_inventory_health_snooze import AgentInventoryHealthSnooze


T = TypeVar("T", bound="AgentInventoryHealth")


@_attrs_define
class AgentInventoryHealth:
    """Whether Watcher was fully on for the machine, from its newest report that carried endpoint health.

    Attributes:
        observed_at (datetime.datetime): When the machine read these values, by its own clock; a time after the report
            arrived, or before 2020, is replaced by the arrival time.
        enforcement_mode (None | str): `enforce` when risky calls can be blocked; `observe` when calls are graded but
            never blocked; `paused` when nothing is evaluated, not even rules. Values may be added. Null when the machine
            could not read it or sent a value this server does not know.
        snooze (AgentInventoryHealthSnooze | None): Whether grading was snoozed; null when the machine could not read
            it.
        agents (list[AgentInventoryHealthAgent] | None): Every coding agent Watcher has hooks for on the machine; null
            when the machine could not read them.
        delivery (AgentInventoryHealthDelivery | None): The upload backlog; null when the machine could not read it.
        self_check (AgentInventoryHealthSelfCheckType0 | None): The machine's background self-check: each `watcher
            doctor` section it ran (`database`, `target`, `hooks`, `enforcement`, `settings`, `decisions`) to its worst
            result (`ok`, `warning` or `error`). Sections and results may be added. A section is missing when its check
            failed to run; the whole value is null when the machine could not run the self-check.
        received_at (datetime.datetime): When the report carrying these values arrived.
        approval_bypass_sessions (int | None | Unset): How many open agent sessions run with an approval policy or
            sandbox that lets tool calls run without asking for approval, so Watcher records their calls but cannot grade or
            block them first: the sessions behind the `enforcement` self-check result (a warning for one to four, an error
            from five). Null when the machine could not check, or from a client too old to count them.
    """

    observed_at: datetime.datetime
    enforcement_mode: None | str
    snooze: AgentInventoryHealthSnooze | None
    agents: list[AgentInventoryHealthAgent] | None
    delivery: AgentInventoryHealthDelivery | None
    self_check: AgentInventoryHealthSelfCheckType0 | None
    received_at: datetime.datetime
    approval_bypass_sessions: int | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.agent_inventory_health_delivery import (
            AgentInventoryHealthDelivery,
        )
        from ..models.agent_inventory_health_self_check_type_0 import (
            AgentInventoryHealthSelfCheckType0,
        )
        from ..models.agent_inventory_health_snooze import AgentInventoryHealthSnooze

        observed_at = self.observed_at.isoformat()

        enforcement_mode: None | str
        enforcement_mode = self.enforcement_mode

        snooze: dict[str, Any] | None
        if isinstance(self.snooze, AgentInventoryHealthSnooze):
            snooze = self.snooze.to_dict()
        else:
            snooze = self.snooze

        agents: list[dict[str, Any]] | None
        if isinstance(self.agents, list):
            agents = []
            for agents_type_0_item_data in self.agents:
                agents_type_0_item = agents_type_0_item_data.to_dict()
                agents.append(agents_type_0_item)

        else:
            agents = self.agents

        delivery: dict[str, Any] | None
        if isinstance(self.delivery, AgentInventoryHealthDelivery):
            delivery = self.delivery.to_dict()
        else:
            delivery = self.delivery

        self_check: dict[str, Any] | None
        if isinstance(self.self_check, AgentInventoryHealthSelfCheckType0):
            self_check = self.self_check.to_dict()
        else:
            self_check = self.self_check

        received_at = self.received_at.isoformat()

        approval_bypass_sessions: int | None | Unset
        if isinstance(self.approval_bypass_sessions, Unset):
            approval_bypass_sessions = UNSET
        else:
            approval_bypass_sessions = self.approval_bypass_sessions

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "observed_at": observed_at,
                "enforcement_mode": enforcement_mode,
                "snooze": snooze,
                "agents": agents,
                "delivery": delivery,
                "self_check": self_check,
                "received_at": received_at,
            }
        )
        if approval_bypass_sessions is not UNSET:
            field_dict["approval_bypass_sessions"] = approval_bypass_sessions

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        from ..models.agent_inventory_health_agent import AgentInventoryHealthAgent
        from ..models.agent_inventory_health_delivery import (
            AgentInventoryHealthDelivery,
        )
        from ..models.agent_inventory_health_self_check_type_0 import (
            AgentInventoryHealthSelfCheckType0,
        )
        from ..models.agent_inventory_health_snooze import AgentInventoryHealthSnooze

        d = dict(src_dict)
        observed_at = datetime.datetime.fromisoformat(d.pop("observed_at"))

        def _parse_enforcement_mode(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        enforcement_mode = _parse_enforcement_mode(d.pop("enforcement_mode"))

        def _parse_snooze(data: object) -> AgentInventoryHealthSnooze | None:
            if data is None:
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                snooze_type_0 = AgentInventoryHealthSnooze.from_dict(data)

                return snooze_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(AgentInventoryHealthSnooze | None, data)

        snooze = _parse_snooze(d.pop("snooze"))

        def _parse_agents(data: object) -> list[AgentInventoryHealthAgent] | None:
            if data is None:
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                agents_type_0 = []
                _agents_type_0 = data
                for agents_type_0_item_data in _agents_type_0:
                    agents_type_0_item = AgentInventoryHealthAgent.from_dict(
                        agents_type_0_item_data
                    )

                    agents_type_0.append(agents_type_0_item)

                return agents_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(list[AgentInventoryHealthAgent] | None, data)

        agents = _parse_agents(d.pop("agents"))

        def _parse_delivery(data: object) -> AgentInventoryHealthDelivery | None:
            if data is None:
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                delivery_type_0 = AgentInventoryHealthDelivery.from_dict(data)

                return delivery_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(AgentInventoryHealthDelivery | None, data)

        delivery = _parse_delivery(d.pop("delivery"))

        def _parse_self_check(
            data: object,
        ) -> AgentInventoryHealthSelfCheckType0 | None:
            if data is None:
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                self_check_type_0 = AgentInventoryHealthSelfCheckType0.from_dict(data)

                return self_check_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(AgentInventoryHealthSelfCheckType0 | None, data)

        self_check = _parse_self_check(d.pop("self_check"))

        received_at = datetime.datetime.fromisoformat(d.pop("received_at"))

        def _parse_approval_bypass_sessions(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        approval_bypass_sessions = _parse_approval_bypass_sessions(
            d.pop("approval_bypass_sessions", UNSET)
        )

        agent_inventory_health = cls(
            observed_at=observed_at,
            enforcement_mode=enforcement_mode,
            snooze=snooze,
            agents=agents,
            delivery=delivery,
            self_check=self_check,
            received_at=received_at,
            approval_bypass_sessions=approval_bypass_sessions,
        )

        agent_inventory_health.additional_properties = d
        return agent_inventory_health

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
