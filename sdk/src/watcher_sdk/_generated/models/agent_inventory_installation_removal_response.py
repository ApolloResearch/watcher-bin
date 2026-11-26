from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import Any, Self, TypeVar
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.agent_inventory_installation_removal_response_result import (
    AgentInventoryInstallationRemovalResponseResult,
)

T = TypeVar("T", bound="AgentInventoryInstallationRemovalResponse")


@_attrs_define
class AgentInventoryInstallationRemovalResponse:
    """What removing a machine from the agent inventory did.

    Attributes:
        installation_id (UUID):
        result (AgentInventoryInstallationRemovalResponseResult): `removed` when this request recorded the removal;
            `already_removed` when the machine was removed before and has not reported since, so nothing changed. The
            machine stays hidden until its Watcher client reports again, which can be at once if a report arrives while the
            removal is recorded.
        removed_at (datetime.datetime): When the removal was recorded; a repeated request returns the original time.
    """

    installation_id: UUID
    result: AgentInventoryInstallationRemovalResponseResult
    removed_at: datetime.datetime
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        installation_id = str(self.installation_id)

        result = self.result.value

        removed_at = self.removed_at.isoformat()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "installation_id": installation_id,
                "result": result,
                "removed_at": removed_at,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        d = dict(src_dict)
        installation_id = UUID(d.pop("installation_id"))

        result = AgentInventoryInstallationRemovalResponseResult(d.pop("result"))

        removed_at = datetime.datetime.fromisoformat(d.pop("removed_at"))

        agent_inventory_installation_removal_response = cls(
            installation_id=installation_id,
            result=result,
            removed_at=removed_at,
        )

        agent_inventory_installation_removal_response.additional_properties = d
        return agent_inventory_installation_removal_response

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
