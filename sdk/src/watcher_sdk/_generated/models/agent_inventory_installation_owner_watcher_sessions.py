from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Self, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="AgentInventoryInstallationOwnerWatcherSessions")


@_attrs_define
class AgentInventoryInstallationOwnerWatcherSessions:
    """The owner's Watcher sessions active in the last 7 days, per agent Watcher can receive sessions from, from any of
    their machines or a gateway; an agent with none is left out. It stands in for the agents' own counts on a machine
    with no inventory scan, whose sessions cannot be matched to it by hostname.

    """

    additional_properties: dict[str, int] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        d = dict(src_dict)
        agent_inventory_installation_owner_watcher_sessions = cls()

        agent_inventory_installation_owner_watcher_sessions.additional_properties = d
        return agent_inventory_installation_owner_watcher_sessions

    @property
    def additional_keys(self) -> list[str]:
        return list(self.additional_properties.keys())

    def __getitem__(self, key: str) -> int:
        return self.additional_properties[key]

    def __setitem__(self, key: str, value: int) -> None:
        self.additional_properties[key] = value

    def __delitem__(self, key: str) -> None:
        del self.additional_properties[key]

    def __contains__(self, key: str) -> bool:
        return key in self.additional_properties
