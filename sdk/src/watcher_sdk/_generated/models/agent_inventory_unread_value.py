from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Self, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.agent_inventory_unread_value_value import AgentInventoryUnreadValueValue
from ..types import UNSET, Unset

T = TypeVar("T", bound="AgentInventoryUnreadValue")


@_attrs_define
class AgentInventoryUnreadValue:
    """One value a complete health reading needs that the machine could not read.

    Attributes:
        value (AgentInventoryUnreadValueValue): `enforcement_mode`, `snooze`, `agents` (missing or empty), an agent's
            `hooks` or `setup`, `uploads` (a count, or the decisions self-check result while decisions wait) or `self_check`
            (the whole result, or a section with none).
        agent (None | str | Unset): The agent, for `hooks` and `setup`; null otherwise.
    """

    value: AgentInventoryUnreadValueValue
    agent: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        value = self.value.value

        agent: None | str | Unset
        if isinstance(self.agent, Unset):
            agent = UNSET
        else:
            agent = self.agent

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "value": value,
            }
        )
        if agent is not UNSET:
            field_dict["agent"] = agent

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        d = dict(src_dict)
        value = AgentInventoryUnreadValueValue(d.pop("value"))

        def _parse_agent(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        agent = _parse_agent(d.pop("agent", UNSET))

        agent_inventory_unread_value = cls(
            value=value,
            agent=agent,
        )

        agent_inventory_unread_value.additional_properties = d
        return agent_inventory_unread_value

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
