from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Self, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.agent_inventory_agent_health_state_state import (
    AgentInventoryAgentHealthStateState,
)

T = TypeVar("T", bound="AgentInventoryAgentHealthState")


@_attrs_define
class AgentInventoryAgentHealthState:
    """One agent's state on the machine, from the health reading.

    Attributes:
        agent (str): The agent's ID, as in `health.agents`.
        state (AgentInventoryAgentHealthStateState): `turned_off` (in Watcher's settings; an agent off whose lock was
            not read counts here), `turned_off_by_organization`, `turned_off_not_found` (off, and not installed), `on`
            (hooks installed and setup current), `setup_out_of_date`, `setup_unknown`, `hooks_missing`, `hooks_untrusted`,
            `hooks_turned_off_in_agent`, `agent_not_found` or `unknown` (hooks not read). Values may be added.
    """

    agent: str
    state: AgentInventoryAgentHealthStateState
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        agent = self.agent

        state = self.state.value

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "agent": agent,
                "state": state,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        d = dict(src_dict)
        agent = d.pop("agent")

        state = AgentInventoryAgentHealthStateState(d.pop("state"))

        agent_inventory_agent_health_state = cls(
            agent=agent,
            state=state,
        )

        agent_inventory_agent_health_state.additional_properties = d
        return agent_inventory_agent_health_state

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
