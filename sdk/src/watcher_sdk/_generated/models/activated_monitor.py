from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from typing_extensions import Self

from ..models.activated_monitor_stages_item import ActivatedMonitorStagesItem

T = TypeVar("T", bound="ActivatedMonitor")


@_attrs_define
class ActivatedMonitor:
    """One monitor selected by the current Watcher Live settings document, and how.

    `grader_id` is the resolved identity: a custom grader ID or a managed monitor
    ID from GET /v1/monitors when a stage uses its shipped default. A managed ID
    is not the settings value selecting that role and is not listed by GET
    /v1/graders. `stages` lists the selected live-pipeline stages; a monitor can
    fill more than one. `enforced` is true only when
    every one of those bindings is locked against local override on machines.

        Attributes:
            grader_id (str):
            stages (list[ActivatedMonitorStagesItem]):
            enforced (bool):
    """

    grader_id: str
    stages: list[ActivatedMonitorStagesItem]
    enforced: bool
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        grader_id = self.grader_id

        stages = []
        for stages_item_data in self.stages:
            stages_item = stages_item_data.value
            stages.append(stages_item)

        enforced = self.enforced

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "grader_id": grader_id,
                "stages": stages,
                "enforced": enforced,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        d = dict(src_dict)
        grader_id = d.pop("grader_id")

        stages = []
        _stages = d.pop("stages")
        for stages_item_data in _stages:
            stages_item = ActivatedMonitorStagesItem(stages_item_data)

            stages.append(stages_item)

        enforced = d.pop("enforced")

        activated_monitor = cls(
            grader_id=grader_id,
            stages=stages,
            enforced=enforced,
        )

        activated_monitor.additional_properties = d
        return activated_monitor

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
