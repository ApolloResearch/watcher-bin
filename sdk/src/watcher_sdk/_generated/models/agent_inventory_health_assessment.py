from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Self, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.agent_inventory_health_assessment_group import (
    AgentInventoryHealthAssessmentGroup,
)

if TYPE_CHECKING:
    from ..models.agent_inventory_agent_health_state import (
        AgentInventoryAgentHealthState,
    )
    from ..models.agent_inventory_health_condition import AgentInventoryHealthCondition


T = TypeVar("T", bound="AgentInventoryHealthAssessment")


@_attrs_define
class AgentInventoryHealthAssessment:
    """What Watcher makes of the machine's check-in, health and inventory, judged when the list was read.

    The rules behind it live on the server only. Judged at one instant, it can go out of date while it is shown:
    once `expires_at` passes, show it as last known rather than working out a new one.

        Attributes:
            group (AgentInventoryHealthAssessmentGroup): `needs_attention` when any condition in `issues` applies to a
                machine that is not merely offline; `offline` when it is offline for less than 7 days (asleep, shut down or no
                reason given), which is expected for laptops; `healthy` otherwise, notes allowed.
            issues (list[AgentInventoryHealthCondition]): The conditions to show, worst severity first; a check-in condition
                always comes first. For an offline machine they include its last known health, which never moves it out of
                `offline`.
            notes (list[AgentInventoryHealthCondition]): Conditions worth knowing that need no action, all with severity
                `note`.
            agents (list[AgentInventoryAgentHealthState]): Each agent in the health reading with its state; empty without a
                health reading.
            health_current_until (datetime.datetime | None): While the health reading is current, when it stops being
                current: its arrival plus one heartbeat window (35 minutes). Null when it was not current at the read (no
                reading, or the machine is not online).
            inventory_current_until (datetime.datetime | None): When the newest inventory scan stops being current: its
                arrival plus a day. Null without a scan.
            expires_at (datetime.datetime | None): The earliest time at which time alone could change this assessment: a
                reading turning stale, an online machine going quiet, an offline one reaching 7 days, a snooze ending. Null when
                only a new report or session can change it.
    """

    group: AgentInventoryHealthAssessmentGroup
    issues: list[AgentInventoryHealthCondition]
    notes: list[AgentInventoryHealthCondition]
    agents: list[AgentInventoryAgentHealthState]
    health_current_until: datetime.datetime | None
    inventory_current_until: datetime.datetime | None
    expires_at: datetime.datetime | None
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        group = self.group.value

        issues = []
        for issues_item_data in self.issues:
            issues_item = issues_item_data.to_dict()
            issues.append(issues_item)

        notes = []
        for notes_item_data in self.notes:
            notes_item = notes_item_data.to_dict()
            notes.append(notes_item)

        agents = []
        for agents_item_data in self.agents:
            agents_item = agents_item_data.to_dict()
            agents.append(agents_item)

        health_current_until: None | str
        if isinstance(self.health_current_until, datetime.datetime):
            health_current_until = self.health_current_until.isoformat()
        else:
            health_current_until = self.health_current_until

        inventory_current_until: None | str
        if isinstance(self.inventory_current_until, datetime.datetime):
            inventory_current_until = self.inventory_current_until.isoformat()
        else:
            inventory_current_until = self.inventory_current_until

        expires_at: None | str
        if isinstance(self.expires_at, datetime.datetime):
            expires_at = self.expires_at.isoformat()
        else:
            expires_at = self.expires_at

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "group": group,
                "issues": issues,
                "notes": notes,
                "agents": agents,
                "health_current_until": health_current_until,
                "inventory_current_until": inventory_current_until,
                "expires_at": expires_at,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        from ..models.agent_inventory_agent_health_state import (
            AgentInventoryAgentHealthState,
        )
        from ..models.agent_inventory_health_condition import (
            AgentInventoryHealthCondition,
        )

        d = dict(src_dict)
        group = AgentInventoryHealthAssessmentGroup(d.pop("group"))

        issues = []
        _issues = d.pop("issues")
        for issues_item_data in _issues:
            issues_item = AgentInventoryHealthCondition.from_dict(issues_item_data)

            issues.append(issues_item)

        notes = []
        _notes = d.pop("notes")
        for notes_item_data in _notes:
            notes_item = AgentInventoryHealthCondition.from_dict(notes_item_data)

            notes.append(notes_item)

        agents = []
        _agents = d.pop("agents")
        for agents_item_data in _agents:
            agents_item = AgentInventoryAgentHealthState.from_dict(agents_item_data)

            agents.append(agents_item)

        def _parse_health_current_until(data: object) -> datetime.datetime | None:
            if data is None:
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                health_current_until_type_0 = datetime.datetime.fromisoformat(data)

                return health_current_until_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None, data)

        health_current_until = _parse_health_current_until(
            d.pop("health_current_until")
        )

        def _parse_inventory_current_until(data: object) -> datetime.datetime | None:
            if data is None:
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                inventory_current_until_type_0 = datetime.datetime.fromisoformat(data)

                return inventory_current_until_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None, data)

        inventory_current_until = _parse_inventory_current_until(
            d.pop("inventory_current_until")
        )

        def _parse_expires_at(data: object) -> datetime.datetime | None:
            if data is None:
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                expires_at_type_0 = datetime.datetime.fromisoformat(data)

                return expires_at_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None, data)

        expires_at = _parse_expires_at(d.pop("expires_at"))

        agent_inventory_health_assessment = cls(
            group=group,
            issues=issues,
            notes=notes,
            agents=agents,
            health_current_until=health_current_until,
            inventory_current_until=inventory_current_until,
            expires_at=expires_at,
        )

        agent_inventory_health_assessment.additional_properties = d
        return agent_inventory_health_assessment

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
