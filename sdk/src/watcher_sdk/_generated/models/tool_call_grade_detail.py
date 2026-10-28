from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Self, TypeVar, cast
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.tool_call_grade_kind import ToolCallGradeKind
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.tool_call_grade_detail_grades import ToolCallGradeDetailGrades
    from ..models.tool_call_grade_detail_input_messages_item import (
        ToolCallGradeDetailInputMessagesItem,
    )


T = TypeVar("T", bound="ToolCallGradeDetail")


@_attrs_define
class ToolCallGradeDetail:
    """Persisted tool-call grade attached to a tool-call decision.

    The row contains the grader output and the kind of tool-call grading run.
    ``input_messages`` (the transcript context the grade was run on) is
    returned empty by transcript-oriented endpoints such as trajectory detail:
    the stored payload is a transcript prefix per tool call, which dwarfs the
    rest of the response and is only needed for grade-provenance audits.

        Attributes:
            grader_id (UUID):
            grades (ToolCallGradeDetailGrades):
            tool_call_grade_id (UUID):
            grader_version (int):
            input_messages (list[ToolCallGradeDetailInputMessagesItem]):
            run_kind (ToolCallGradeKind): Tool-call grader run types attached to a tool-call decision.
            created_at (datetime.datetime):
            model (None | str | Unset):
            error (None | str | Unset):
    """

    grader_id: UUID
    grades: ToolCallGradeDetailGrades
    tool_call_grade_id: UUID
    grader_version: int
    input_messages: list[ToolCallGradeDetailInputMessagesItem]
    run_kind: ToolCallGradeKind
    created_at: datetime.datetime
    model: None | str | Unset = UNSET
    error: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        grader_id = str(self.grader_id)

        grades = self.grades.to_dict()

        tool_call_grade_id = str(self.tool_call_grade_id)

        grader_version = self.grader_version

        input_messages = []
        for input_messages_item_data in self.input_messages:
            input_messages_item = input_messages_item_data.to_dict()
            input_messages.append(input_messages_item)

        run_kind = self.run_kind.value

        created_at = self.created_at.isoformat()

        model: None | str | Unset
        if isinstance(self.model, Unset):
            model = UNSET
        else:
            model = self.model

        error: None | str | Unset
        if isinstance(self.error, Unset):
            error = UNSET
        else:
            error = self.error

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "grader_id": grader_id,
                "grades": grades,
                "tool_call_grade_id": tool_call_grade_id,
                "grader_version": grader_version,
                "input_messages": input_messages,
                "run_kind": run_kind,
                "created_at": created_at,
            }
        )
        if model is not UNSET:
            field_dict["model"] = model
        if error is not UNSET:
            field_dict["error"] = error

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        from ..models.tool_call_grade_detail_grades import ToolCallGradeDetailGrades
        from ..models.tool_call_grade_detail_input_messages_item import (
            ToolCallGradeDetailInputMessagesItem,
        )

        d = dict(src_dict)
        grader_id = UUID(d.pop("grader_id"))

        grades = ToolCallGradeDetailGrades.from_dict(d.pop("grades"))

        tool_call_grade_id = UUID(d.pop("tool_call_grade_id"))

        grader_version = d.pop("grader_version")

        input_messages = []
        _input_messages = d.pop("input_messages")
        for input_messages_item_data in _input_messages:
            input_messages_item = ToolCallGradeDetailInputMessagesItem.from_dict(
                input_messages_item_data
            )

            input_messages.append(input_messages_item)

        run_kind = ToolCallGradeKind(d.pop("run_kind"))

        created_at = datetime.datetime.fromisoformat(d.pop("created_at"))

        def _parse_model(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        model = _parse_model(d.pop("model", UNSET))

        def _parse_error(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        error = _parse_error(d.pop("error", UNSET))

        tool_call_grade_detail = cls(
            grader_id=grader_id,
            grades=grades,
            tool_call_grade_id=tool_call_grade_id,
            grader_version=grader_version,
            input_messages=input_messages,
            run_kind=run_kind,
            created_at=created_at,
            model=model,
            error=error,
        )

        tool_call_grade_detail.additional_properties = d
        return tool_call_grade_detail

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
