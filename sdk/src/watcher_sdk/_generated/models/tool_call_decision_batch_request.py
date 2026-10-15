from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from typing_extensions import Self

if TYPE_CHECKING:
    from ..models.tool_call_decision_payload import ToolCallDecisionPayload


T = TypeVar("T", bound="ToolCallDecisionBatchRequest")


@_attrs_define
class ToolCallDecisionBatchRequest:
    """Batch upload tool-call decisions after transcript ingest.

    Every decision should refer to a tool-use block already present in the
    session's messages. Valid decisions are persisted even when other items in
    the same batch cannot be resolved.

        Attributes:
            session_id (UUID):
            decisions (list[ToolCallDecisionPayload]):
    """

    session_id: UUID
    decisions: list[ToolCallDecisionPayload]
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        session_id = str(self.session_id)

        decisions = []
        for decisions_item_data in self.decisions:
            decisions_item = decisions_item_data.to_dict()
            decisions.append(decisions_item)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "session_id": session_id,
                "decisions": decisions,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        from ..models.tool_call_decision_payload import (
            ToolCallDecisionPayload,
        )

        d = dict(src_dict)
        session_id = UUID(d.pop("session_id"))

        decisions = []
        _decisions = d.pop("decisions")
        for decisions_item_data in _decisions:
            decisions_item = ToolCallDecisionPayload.from_dict(decisions_item_data)

            decisions.append(decisions_item)

        tool_call_decision_batch_request = cls(
            session_id=session_id,
            decisions=decisions,
        )

        tool_call_decision_batch_request.additional_properties = d
        return tool_call_decision_batch_request

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
