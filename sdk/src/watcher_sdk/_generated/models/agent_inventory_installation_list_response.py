from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Self, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.agent_inventory_installation import AgentInventoryInstallation


T = TypeVar("T", bound="AgentInventoryInstallationListResponse")


@_attrs_define
class AgentInventoryInstallationListResponse:
    """A page of machines, most recently reported first.

    Attributes:
        installations (list[AgentInventoryInstallation]):
        total (int):
        limit (int):
        offset (int):
    """

    installations: list[AgentInventoryInstallation]
    total: int
    limit: int
    offset: int
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        installations = []
        for installations_item_data in self.installations:
            installations_item = installations_item_data.to_dict()
            installations.append(installations_item)

        total = self.total

        limit = self.limit

        offset = self.offset

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "installations": installations,
                "total": total,
                "limit": limit,
                "offset": offset,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        from ..models.agent_inventory_installation import AgentInventoryInstallation

        d = dict(src_dict)
        installations = []
        _installations = d.pop("installations")
        for installations_item_data in _installations:
            installations_item = AgentInventoryInstallation.from_dict(
                installations_item_data
            )

            installations.append(installations_item)

        total = d.pop("total")

        limit = d.pop("limit")

        offset = d.pop("offset")

        agent_inventory_installation_list_response = cls(
            installations=installations,
            total=total,
            limit=limit,
            offset=offset,
        )

        agent_inventory_installation_list_response.additional_properties = d
        return agent_inventory_installation_list_response

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
