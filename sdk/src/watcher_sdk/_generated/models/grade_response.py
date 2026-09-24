from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.grade_result import GradeResult


T = TypeVar("T", bound="GradeResponse")


@_attrs_define
class GradeResponse:
    """Response from POST /v1/grade.

    Attributes:
        grades (list[GradeResult]):
        not_found_ids (list[str] | Unset):
    """

    grades: list[GradeResult]
    not_found_ids: list[str] | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        grades = []
        for grades_item_data in self.grades:
            grades_item = grades_item_data.to_dict()
            grades.append(grades_item)

        not_found_ids: list[str] | Unset = UNSET
        if not isinstance(self.not_found_ids, Unset):
            not_found_ids = self.not_found_ids

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "grades": grades,
            }
        )
        if not_found_ids is not UNSET:
            field_dict["not_found_ids"] = not_found_ids

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.grade_result import GradeResult

        d = dict(src_dict)
        grades = []
        _grades = d.pop("grades")
        for grades_item_data in _grades:
            grades_item = GradeResult.from_dict(grades_item_data)

            grades.append(grades_item)

        not_found_ids = cast(list[str], d.pop("not_found_ids", UNSET))

        grade_response = cls(
            grades=grades,
            not_found_ids=not_found_ids,
        )

        grade_response.additional_properties = d
        return grade_response

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
