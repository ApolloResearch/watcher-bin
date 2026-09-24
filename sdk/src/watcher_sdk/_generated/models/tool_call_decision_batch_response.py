from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="ToolCallDecisionBatchResponse")


@_attrs_define
class ToolCallDecisionBatchResponse:
    """Result of a tool-call decision batch upload.

    ``synced_tool_use_ids`` identifies decisions accepted by the server.
    ``failed_tool_use_ids`` and ``failed_tool_call_grade_ids`` identify items
    that were not persisted or linked.

        Attributes:
            synced_count (int):
            synced_tool_use_ids (list[str] | Unset):
            failed_tool_use_ids (list[str] | Unset):
            failed_tool_call_grade_ids (list[UUID] | Unset):
    """

    synced_count: int
    synced_tool_use_ids: list[str] | Unset = UNSET
    failed_tool_use_ids: list[str] | Unset = UNSET
    failed_tool_call_grade_ids: list[UUID] | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        synced_count = self.synced_count

        synced_tool_use_ids: list[str] | Unset = UNSET
        if not isinstance(self.synced_tool_use_ids, Unset):
            synced_tool_use_ids = self.synced_tool_use_ids

        failed_tool_use_ids: list[str] | Unset = UNSET
        if not isinstance(self.failed_tool_use_ids, Unset):
            failed_tool_use_ids = self.failed_tool_use_ids

        failed_tool_call_grade_ids: list[str] | Unset = UNSET
        if not isinstance(self.failed_tool_call_grade_ids, Unset):
            failed_tool_call_grade_ids = []
            for failed_tool_call_grade_ids_item_data in self.failed_tool_call_grade_ids:
                failed_tool_call_grade_ids_item = str(
                    failed_tool_call_grade_ids_item_data
                )
                failed_tool_call_grade_ids.append(failed_tool_call_grade_ids_item)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "synced_count": synced_count,
            }
        )
        if synced_tool_use_ids is not UNSET:
            field_dict["synced_tool_use_ids"] = synced_tool_use_ids
        if failed_tool_use_ids is not UNSET:
            field_dict["failed_tool_use_ids"] = failed_tool_use_ids
        if failed_tool_call_grade_ids is not UNSET:
            field_dict["failed_tool_call_grade_ids"] = failed_tool_call_grade_ids

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        synced_count = d.pop("synced_count")

        synced_tool_use_ids = cast(list[str], d.pop("synced_tool_use_ids", UNSET))

        failed_tool_use_ids = cast(list[str], d.pop("failed_tool_use_ids", UNSET))

        _failed_tool_call_grade_ids = d.pop("failed_tool_call_grade_ids", UNSET)
        failed_tool_call_grade_ids: list[UUID] | Unset = UNSET
        if _failed_tool_call_grade_ids is not UNSET:
            failed_tool_call_grade_ids = []
            for failed_tool_call_grade_ids_item_data in _failed_tool_call_grade_ids:
                failed_tool_call_grade_ids_item = UUID(
                    failed_tool_call_grade_ids_item_data
                )

                failed_tool_call_grade_ids.append(failed_tool_call_grade_ids_item)

        tool_call_decision_batch_response = cls(
            synced_count=synced_count,
            synced_tool_use_ids=synced_tool_use_ids,
            failed_tool_use_ids=failed_tool_use_ids,
            failed_tool_call_grade_ids=failed_tool_call_grade_ids,
        )

        tool_call_decision_batch_response.additional_properties = d
        return tool_call_decision_batch_response

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
