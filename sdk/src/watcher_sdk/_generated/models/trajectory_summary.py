from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from typing_extensions import Self

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.grade_result import GradeResult


T = TypeVar("T", bound="TrajectorySummary")


@_attrs_define
class TrajectorySummary:
    """Summary of a trajectory for list responses.

    Attributes:
        trajectory_id (str):
        message_count (int):
        first_timestamp (datetime.datetime):
        last_timestamp (datetime.datetime):
        source (str):
        session_id (str):
        grades (list[GradeResult] | Unset):
    """

    trajectory_id: str
    message_count: int
    first_timestamp: datetime.datetime
    last_timestamp: datetime.datetime
    source: str
    session_id: str
    grades: list[GradeResult] | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        trajectory_id = self.trajectory_id

        message_count = self.message_count

        first_timestamp = self.first_timestamp.isoformat()

        last_timestamp = self.last_timestamp.isoformat()

        source = self.source

        session_id = self.session_id

        grades: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.grades, Unset):
            grades = []
            for grades_item_data in self.grades:
                grades_item = grades_item_data.to_dict()
                grades.append(grades_item)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "trajectory_id": trajectory_id,
                "message_count": message_count,
                "first_timestamp": first_timestamp,
                "last_timestamp": last_timestamp,
                "source": source,
                "session_id": session_id,
            }
        )
        if grades is not UNSET:
            field_dict["grades"] = grades

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        from ..models.grade_result import GradeResult

        d = dict(src_dict)
        trajectory_id = d.pop("trajectory_id")

        message_count = d.pop("message_count")

        first_timestamp = datetime.datetime.fromisoformat(d.pop("first_timestamp"))

        last_timestamp = datetime.datetime.fromisoformat(d.pop("last_timestamp"))

        source = d.pop("source")

        session_id = d.pop("session_id")

        _grades = d.pop("grades", UNSET)
        grades: list[GradeResult] | Unset = UNSET
        if _grades is not UNSET:
            grades = []
            for grades_item_data in _grades:
                grades_item = GradeResult.from_dict(grades_item_data)

                grades.append(grades_item)

        trajectory_summary = cls(
            trajectory_id=trajectory_id,
            message_count=message_count,
            first_timestamp=first_timestamp,
            last_timestamp=last_timestamp,
            source=source,
            session_id=session_id,
            grades=grades,
        )

        trajectory_summary.additional_properties = d
        return trajectory_summary

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
