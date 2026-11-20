from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Self, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.agent_inventory_self_check_finding_result import (
    AgentInventorySelfCheckFindingResult,
)

T = TypeVar("T", bound="AgentInventorySelfCheckFinding")


@_attrs_define
class AgentInventorySelfCheckFinding:
    """One background self-check section that flagged a warning or an error.

    Attributes:
        section (str): The `watcher doctor` section, as in the health reading's `self_check`.
        result (AgentInventorySelfCheckFindingResult):
    """

    section: str
    result: AgentInventorySelfCheckFindingResult
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        section = self.section

        result = self.result.value

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "section": section,
                "result": result,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        d = dict(src_dict)
        section = d.pop("section")

        result = AgentInventorySelfCheckFindingResult(d.pop("result"))

        agent_inventory_self_check_finding = cls(
            section=section,
            result=result,
        )

        agent_inventory_self_check_finding.additional_properties = d
        return agent_inventory_self_check_finding

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
