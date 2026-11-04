from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Self, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.agent_inventory_gateway_client import AgentInventoryGatewayClient


T = TypeVar("T", bound="AgentInventoryGatewaySummary")


@_attrs_define
class AgentInventoryGatewaySummary:
    """Clients seen in traffic through gateways connected to Watcher in the last 7 days.

    Attributes:
        people (int): People with any gateway traffic in the last 7 days.
        unrecognized_people (int): People seen using any unrecognized client in the last 7 days.
        only_at_gateway (list[AgentInventoryGatewayClient]): Every unrecognized client, and recognized agents used at
            the gateway by people with no machine reporting that agent's recent use.
    """

    people: int
    unrecognized_people: int
    only_at_gateway: list[AgentInventoryGatewayClient]
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        people = self.people

        unrecognized_people = self.unrecognized_people

        only_at_gateway = []
        for only_at_gateway_item_data in self.only_at_gateway:
            only_at_gateway_item = only_at_gateway_item_data.to_dict()
            only_at_gateway.append(only_at_gateway_item)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "people": people,
                "unrecognized_people": unrecognized_people,
                "only_at_gateway": only_at_gateway,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        from ..models.agent_inventory_gateway_client import AgentInventoryGatewayClient

        d = dict(src_dict)
        people = d.pop("people")

        unrecognized_people = d.pop("unrecognized_people")

        only_at_gateway = []
        _only_at_gateway = d.pop("only_at_gateway")
        for only_at_gateway_item_data in _only_at_gateway:
            only_at_gateway_item = AgentInventoryGatewayClient.from_dict(
                only_at_gateway_item_data
            )

            only_at_gateway.append(only_at_gateway_item)

        agent_inventory_gateway_summary = cls(
            people=people,
            unrecognized_people=unrecognized_people,
            only_at_gateway=only_at_gateway,
        )

        agent_inventory_gateway_summary.additional_properties = d
        return agent_inventory_gateway_summary

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
