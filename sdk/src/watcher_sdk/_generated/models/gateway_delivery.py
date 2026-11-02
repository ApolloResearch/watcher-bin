from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Self, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.gateway_action import GatewayAction

T = TypeVar("T", bound="GatewayDelivery")


@_attrs_define
class GatewayDelivery:
    """Where a gateway delivered another response in place of a tool call it withheld.

    ``action`` describes delivery only; the call's decision keeps Watcher's own
    verdict. Both refs are ``message_ref`` values of messages stored in the
    call's session.

        Attributes:
            action (GatewayAction): What a gateway did with a tool call it did not deliver to the client.

                ``blocked``: the gateway refused the call because Watcher denied or
                escalated it. ``cancelled``: Watcher did not refuse the call, but the
                gateway dropped it with a refused call from the same proposal.
            delivered_message_ref (str): Message the gateway delivered to the client instead.
            proposal_message_ref (str): Message that proposed the call, on its own branch.
    """

    action: GatewayAction
    delivered_message_ref: str
    proposal_message_ref: str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        action = self.action.value

        delivered_message_ref = self.delivered_message_ref

        proposal_message_ref = self.proposal_message_ref

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "action": action,
                "delivered_message_ref": delivered_message_ref,
                "proposal_message_ref": proposal_message_ref,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        d = dict(src_dict)
        action = GatewayAction(d.pop("action"))

        delivered_message_ref = d.pop("delivered_message_ref")

        proposal_message_ref = d.pop("proposal_message_ref")

        gateway_delivery = cls(
            action=action,
            delivered_message_ref=delivered_message_ref,
            proposal_message_ref=proposal_message_ref,
        )

        gateway_delivery.additional_properties = d
        return gateway_delivery

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
