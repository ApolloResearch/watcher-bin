from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Self, TypeVar, cast
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.agent_inventory_user_agent import AgentInventoryUserAgent
    from ..models.agent_inventory_user_machine import AgentInventoryUserMachine


T = TypeVar("T", bound="AgentInventoryUser")


@_attrs_define
class AgentInventoryUser:
    """One person seen in the last 7 days, with their machines and the agents they used.

    Attributes:
        key (str): Identifies the person in this list: `user:<user ID>` for a Watcher user, including people a gateway
            named, or `gateway:no-identity` for gateway traffic that named nobody.
        user_id (None | UUID):
        user_name (None | str):
        user_email (None | str): Hidden unless you may read other people's email addresses.
        last_report_at (datetime.datetime | None): The newest report from any of their machines.
        machines (list[AgentInventoryUserMachine]): All their machines, most recently reported first.
        agents (list[AgentInventoryUserAgent]): The agents they used in the last 7 days.
    """

    key: str
    user_id: None | UUID
    user_name: None | str
    user_email: None | str
    last_report_at: datetime.datetime | None
    machines: list[AgentInventoryUserMachine]
    agents: list[AgentInventoryUserAgent]
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        key = self.key

        user_id: None | str
        if isinstance(self.user_id, UUID):
            user_id = str(self.user_id)
        else:
            user_id = self.user_id

        user_name: None | str
        user_name = self.user_name

        user_email: None | str
        user_email = self.user_email

        last_report_at: None | str
        if isinstance(self.last_report_at, datetime.datetime):
            last_report_at = self.last_report_at.isoformat()
        else:
            last_report_at = self.last_report_at

        machines = []
        for machines_item_data in self.machines:
            machines_item = machines_item_data.to_dict()
            machines.append(machines_item)

        agents = []
        for agents_item_data in self.agents:
            agents_item = agents_item_data.to_dict()
            agents.append(agents_item)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "key": key,
                "user_id": user_id,
                "user_name": user_name,
                "user_email": user_email,
                "last_report_at": last_report_at,
                "machines": machines,
                "agents": agents,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        from ..models.agent_inventory_user_agent import AgentInventoryUserAgent
        from ..models.agent_inventory_user_machine import AgentInventoryUserMachine

        d = dict(src_dict)
        key = d.pop("key")

        def _parse_user_id(data: object) -> None | UUID:
            if data is None:
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                user_id_type_0 = UUID(data)

                return user_id_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | UUID, data)

        user_id = _parse_user_id(d.pop("user_id"))

        def _parse_user_name(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        user_name = _parse_user_name(d.pop("user_name"))

        def _parse_user_email(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        user_email = _parse_user_email(d.pop("user_email"))

        def _parse_last_report_at(data: object) -> datetime.datetime | None:
            if data is None:
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                last_report_at_type_0 = datetime.datetime.fromisoformat(data)

                return last_report_at_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None, data)

        last_report_at = _parse_last_report_at(d.pop("last_report_at"))

        machines = []
        _machines = d.pop("machines")
        for machines_item_data in _machines:
            machines_item = AgentInventoryUserMachine.from_dict(machines_item_data)

            machines.append(machines_item)

        agents = []
        _agents = d.pop("agents")
        for agents_item_data in _agents:
            agents_item = AgentInventoryUserAgent.from_dict(agents_item_data)

            agents.append(agents_item)

        agent_inventory_user = cls(
            key=key,
            user_id=user_id,
            user_name=user_name,
            user_email=user_email,
            last_report_at=last_report_at,
            machines=machines,
            agents=agents,
        )

        agent_inventory_user.additional_properties = d
        return agent_inventory_user

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
