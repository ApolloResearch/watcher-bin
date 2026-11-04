from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import Any, Self, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="AgentInventoryGatewayClient")


@_attrs_define
class AgentInventoryGatewayClient:
    """A client seen only in gateway traffic in the last 7 days.

    Attributes:
        client_name (str): An agent ID for recognized agents, otherwise the product name from the user agent.
        recognized (bool): Whether the client is an agent the inventory knows.
        people (int): People seen using it at the gateway who have no machine reporting it.
        last_seen_at (datetime.datetime):
    """

    client_name: str
    recognized: bool
    people: int
    last_seen_at: datetime.datetime
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        client_name = self.client_name

        recognized = self.recognized

        people = self.people

        last_seen_at = self.last_seen_at.isoformat()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "client_name": client_name,
                "recognized": recognized,
                "people": people,
                "last_seen_at": last_seen_at,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        d = dict(src_dict)
        client_name = d.pop("client_name")

        recognized = d.pop("recognized")

        people = d.pop("people")

        last_seen_at = datetime.datetime.fromisoformat(d.pop("last_seen_at"))

        agent_inventory_gateway_client = cls(
            client_name=client_name,
            recognized=recognized,
            people=people,
            last_seen_at=last_seen_at,
        )

        agent_inventory_gateway_client.additional_properties = d
        return agent_inventory_gateway_client

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
