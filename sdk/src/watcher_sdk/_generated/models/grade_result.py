from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from typing_extensions import Self

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.grade_result_grades import GradeResultGrades


T = TypeVar("T", bound="GradeResult")


@_attrs_define
class GradeResult:
    """API representation of a trajectory grade.

    DB-backed grades include trajectory and session identifiers. Ephemeral
    grades omit persisted trajectory identifiers and use ``trajectory_index`` to
    identify the trajectory's position in the request.

    Stored session summaries (including nested report summaries) require content
    access. Mixed read responses omit fields outside the caller's read permissions.

    Callers can resolve ``(grader_id, grader_version)`` to the exact grader
    configuration used via GET /v1/graders/{grader_id}/{version}.

        Attributes:
            grader_id (UUID):
            grades (GradeResultGrades):
            model (None | str | Unset):
            error (None | str | Unset):
            trajectory_hash (None | str | Unset):
            grader_version (int | None | Unset):
            session_id (None | Unset | UUID):
            created_at (datetime.datetime | None | Unset):
            trajectory_index (int | None | Unset):
            tool_call_grade_id (None | Unset | UUID):
    """

    grader_id: UUID
    grades: GradeResultGrades
    model: None | str | Unset = UNSET
    error: None | str | Unset = UNSET
    trajectory_hash: None | str | Unset = UNSET
    grader_version: int | None | Unset = UNSET
    session_id: None | Unset | UUID = UNSET
    created_at: datetime.datetime | None | Unset = UNSET
    trajectory_index: int | None | Unset = UNSET
    tool_call_grade_id: None | Unset | UUID = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        grader_id = str(self.grader_id)

        grades = self.grades.to_dict()

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

        trajectory_hash: None | str | Unset
        if isinstance(self.trajectory_hash, Unset):
            trajectory_hash = UNSET
        else:
            trajectory_hash = self.trajectory_hash

        grader_version: int | None | Unset
        if isinstance(self.grader_version, Unset):
            grader_version = UNSET
        else:
            grader_version = self.grader_version

        session_id: None | str | Unset
        if isinstance(self.session_id, Unset):
            session_id = UNSET
        elif isinstance(self.session_id, UUID):
            session_id = str(self.session_id)
        else:
            session_id = self.session_id

        created_at: None | str | Unset
        if isinstance(self.created_at, Unset):
            created_at = UNSET
        elif isinstance(self.created_at, datetime.datetime):
            created_at = self.created_at.isoformat()
        else:
            created_at = self.created_at

        trajectory_index: int | None | Unset
        if isinstance(self.trajectory_index, Unset):
            trajectory_index = UNSET
        else:
            trajectory_index = self.trajectory_index

        tool_call_grade_id: None | str | Unset
        if isinstance(self.tool_call_grade_id, Unset):
            tool_call_grade_id = UNSET
        elif isinstance(self.tool_call_grade_id, UUID):
            tool_call_grade_id = str(self.tool_call_grade_id)
        else:
            tool_call_grade_id = self.tool_call_grade_id

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "grader_id": grader_id,
                "grades": grades,
            }
        )
        if model is not UNSET:
            field_dict["model"] = model
        if error is not UNSET:
            field_dict["error"] = error
        if trajectory_hash is not UNSET:
            field_dict["trajectory_hash"] = trajectory_hash
        if grader_version is not UNSET:
            field_dict["grader_version"] = grader_version
        if session_id is not UNSET:
            field_dict["session_id"] = session_id
        if created_at is not UNSET:
            field_dict["created_at"] = created_at
        if trajectory_index is not UNSET:
            field_dict["trajectory_index"] = trajectory_index
        if tool_call_grade_id is not UNSET:
            field_dict["tool_call_grade_id"] = tool_call_grade_id

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        from ..models.grade_result_grades import GradeResultGrades

        d = dict(src_dict)
        grader_id = UUID(d.pop("grader_id"))

        grades = GradeResultGrades.from_dict(d.pop("grades"))

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

        def _parse_trajectory_hash(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        trajectory_hash = _parse_trajectory_hash(d.pop("trajectory_hash", UNSET))

        def _parse_grader_version(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        grader_version = _parse_grader_version(d.pop("grader_version", UNSET))

        def _parse_session_id(data: object) -> None | Unset | UUID:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                session_id_type_0 = UUID(data)

                return session_id_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | Unset | UUID, data)

        session_id = _parse_session_id(d.pop("session_id", UNSET))

        def _parse_created_at(data: object) -> datetime.datetime | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                created_at_type_0 = datetime.datetime.fromisoformat(data)

                return created_at_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None | Unset, data)

        created_at = _parse_created_at(d.pop("created_at", UNSET))

        def _parse_trajectory_index(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        trajectory_index = _parse_trajectory_index(d.pop("trajectory_index", UNSET))

        def _parse_tool_call_grade_id(data: object) -> None | Unset | UUID:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                tool_call_grade_id_type_0 = UUID(data)

                return tool_call_grade_id_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | Unset | UUID, data)

        tool_call_grade_id = _parse_tool_call_grade_id(
            d.pop("tool_call_grade_id", UNSET)
        )

        grade_result = cls(
            grader_id=grader_id,
            grades=grades,
            model=model,
            error=error,
            trajectory_hash=trajectory_hash,
            grader_version=grader_version,
            session_id=session_id,
            created_at=created_at,
            trajectory_index=trajectory_index,
            tool_call_grade_id=tool_call_grade_id,
        )

        grade_result.additional_properties = d
        return grade_result

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
