from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Self, TypeVar
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.tool_call_record_result import ToolCallRecordResult


T = TypeVar("T", bound="ToolCallRecordsResponse")


@_attrs_define
class ToolCallRecordsResponse:
    """The session the records were filed under and each record's outcome.

    Attributes:
        session_id (UUID): Watcher's ID for the session the records belong to.
        records (list[ToolCallRecordResult]): One result per distinct tool_use_id, in request order.
    """

    session_id: UUID
    records: list[ToolCallRecordResult]
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        session_id = str(self.session_id)

        records = []
        for records_item_data in self.records:
            records_item = records_item_data.to_dict()
            records.append(records_item)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "session_id": session_id,
                "records": records,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        from ..models.tool_call_record_result import ToolCallRecordResult

        d = dict(src_dict)
        session_id = UUID(d.pop("session_id"))

        records = []
        _records = d.pop("records")
        for records_item_data in _records:
            records_item = ToolCallRecordResult.from_dict(records_item_data)

            records.append(records_item)

        tool_call_records_response = cls(
            session_id=session_id,
            records=records,
        )

        tool_call_records_response.additional_properties = d
        return tool_call_records_response

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
