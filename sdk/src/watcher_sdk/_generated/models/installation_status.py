from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Self, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.agent_inventory_status import AgentInventoryStatus


T = TypeVar("T", bound="InstallationStatus")


@_attrs_define
class InstallationStatus:
    """What the installation is reporting, by section. Omit a section to report nothing about it.

    Attributes:
        inventory (AgentInventoryStatus | None | Unset): The coding agents found on the machine, when agent inventory is
            on.
    """

    inventory: AgentInventoryStatus | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.agent_inventory_status import AgentInventoryStatus

        inventory: dict[str, Any] | None | Unset
        if isinstance(self.inventory, Unset):
            inventory = UNSET
        elif isinstance(self.inventory, AgentInventoryStatus):
            inventory = self.inventory.to_dict()
        else:
            inventory = self.inventory

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if inventory is not UNSET:
            field_dict["inventory"] = inventory

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        from ..models.agent_inventory_status import AgentInventoryStatus

        d = dict(src_dict)

        def _parse_inventory(data: object) -> AgentInventoryStatus | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                inventory_type_0 = AgentInventoryStatus.from_dict(data)

                return inventory_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(AgentInventoryStatus | None | Unset, data)

        inventory = _parse_inventory(d.pop("inventory", UNSET))

        installation_status = cls(
            inventory=inventory,
        )

        installation_status.additional_properties = d
        return installation_status

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
