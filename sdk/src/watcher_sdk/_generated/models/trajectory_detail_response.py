from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from dateutil.parser import isoparse

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.grade_result import GradeResult
    from ..models.trajectory_detail_response_messages_item import (
        TrajectoryDetailResponseMessagesItem,
    )
    from ..models.trajectory_detail_response_metadata import (
        TrajectoryDetailResponseMetadata,
    )
    from ..models.trajectory_detail_response_tool_call_decisions import (
        TrajectoryDetailResponseToolCallDecisions,
    )


T = TypeVar("T", bound="TrajectoryDetailResponse")


@_attrs_define
class TrajectoryDetailResponse:
    """Full trajectory detail from GET /v1/trajectories/{id} or /sessions/{sid}/trajectories/{tid}.

    Attributes:
        trajectory_id (str):
        messages (list[TrajectoryDetailResponseMessagesItem]):
        grades (list[GradeResult]):
        metadata (TrajectoryDetailResponseMetadata):
        session_id (str):
        source (str):
        created_at (datetime.datetime):
        tool_call_decisions (TrajectoryDetailResponseToolCallDecisions | Unset):
    """

    trajectory_id: str
    messages: list[TrajectoryDetailResponseMessagesItem]
    grades: list[GradeResult]
    metadata: TrajectoryDetailResponseMetadata
    session_id: str
    source: str
    created_at: datetime.datetime
    tool_call_decisions: TrajectoryDetailResponseToolCallDecisions | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        trajectory_id = self.trajectory_id

        messages = []
        for messages_item_data in self.messages:
            messages_item = messages_item_data.to_dict()
            messages.append(messages_item)

        grades = []
        for grades_item_data in self.grades:
            grades_item = grades_item_data.to_dict()
            grades.append(grades_item)

        metadata = self.metadata.to_dict()

        session_id = self.session_id

        source = self.source

        created_at = self.created_at.isoformat()

        tool_call_decisions: dict[str, Any] | Unset = UNSET
        if not isinstance(self.tool_call_decisions, Unset):
            tool_call_decisions = self.tool_call_decisions.to_dict()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "trajectory_id": trajectory_id,
                "messages": messages,
                "grades": grades,
                "metadata": metadata,
                "session_id": session_id,
                "source": source,
                "created_at": created_at,
            }
        )
        if tool_call_decisions is not UNSET:
            field_dict["tool_call_decisions"] = tool_call_decisions

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.grade_result import GradeResult
        from ..models.trajectory_detail_response_messages_item import (
            TrajectoryDetailResponseMessagesItem,
        )
        from ..models.trajectory_detail_response_metadata import (
            TrajectoryDetailResponseMetadata,
        )
        from ..models.trajectory_detail_response_tool_call_decisions import (
            TrajectoryDetailResponseToolCallDecisions,
        )

        d = dict(src_dict)
        trajectory_id = d.pop("trajectory_id")

        messages = []
        _messages = d.pop("messages")
        for messages_item_data in _messages:
            messages_item = TrajectoryDetailResponseMessagesItem.from_dict(
                messages_item_data
            )

            messages.append(messages_item)

        grades = []
        _grades = d.pop("grades")
        for grades_item_data in _grades:
            grades_item = GradeResult.from_dict(grades_item_data)

            grades.append(grades_item)

        metadata = TrajectoryDetailResponseMetadata.from_dict(d.pop("metadata"))

        session_id = d.pop("session_id")

        source = d.pop("source")

        created_at = isoparse(d.pop("created_at"))

        _tool_call_decisions = d.pop("tool_call_decisions", UNSET)
        tool_call_decisions: TrajectoryDetailResponseToolCallDecisions | Unset
        if isinstance(_tool_call_decisions, Unset):
            tool_call_decisions = UNSET
        else:
            tool_call_decisions = TrajectoryDetailResponseToolCallDecisions.from_dict(
                _tool_call_decisions
            )

        trajectory_detail_response = cls(
            trajectory_id=trajectory_id,
            messages=messages,
            grades=grades,
            metadata=metadata,
            session_id=session_id,
            source=source,
            created_at=created_at,
            tool_call_decisions=tool_call_decisions,
        )

        trajectory_detail_response.additional_properties = d
        return trajectory_detail_response

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
