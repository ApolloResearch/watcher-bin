from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Self, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.grade_result import GradeResult


T = TypeVar("T", bound="GradeResponse")


@_attrs_define
class GradeResponse:
    """Results from UUID-addressed or role-addressed grading.

    Role grading also reports the cost across every trajectory and retry in
    this request. Only the selected role runs: an input triage assessment is
    not another billed stage. Stored-session cost requires findings or content
    read access to that session. UUID-addressed grading leaves cost unknown.
    Older servers omit the field, so clients must accept an absent value.

        Attributes:
            grades (list[GradeResult]):
            not_found_ids (list[str] | Unset):
            cost_usd (float | None | Unset): Estimated USD cost of this request, including retries with reported usage, at
                prices set on the server. Null for UUID-addressed grading, missing usage or pricing, or stored-session grading
                without findings or content read access to that session. Otherwise zero when no model is called. Provider
                attempts whose usage is hidden by the provider client cannot be included.
    """

    grades: list[GradeResult]
    not_found_ids: list[str] | Unset = UNSET
    cost_usd: float | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        grades = []
        for grades_item_data in self.grades:
            grades_item = grades_item_data.to_dict()
            grades.append(grades_item)

        not_found_ids: list[str] | Unset = UNSET
        if not isinstance(self.not_found_ids, Unset):
            not_found_ids = self.not_found_ids

        cost_usd: float | None | Unset
        if isinstance(self.cost_usd, Unset):
            cost_usd = UNSET
        else:
            cost_usd = self.cost_usd

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "grades": grades,
            }
        )
        if not_found_ids is not UNSET:
            field_dict["not_found_ids"] = not_found_ids
        if cost_usd is not UNSET:
            field_dict["cost_usd"] = cost_usd

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        from ..models.grade_result import GradeResult

        d = dict(src_dict)
        grades = []
        _grades = d.pop("grades")
        for grades_item_data in _grades:
            grades_item = GradeResult.from_dict(grades_item_data)

            grades.append(grades_item)

        not_found_ids = cast(list[str], d.pop("not_found_ids", UNSET))

        def _parse_cost_usd(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        cost_usd = _parse_cost_usd(d.pop("cost_usd", UNSET))

        grade_response = cls(
            grades=grades,
            not_found_ids=not_found_ids,
            cost_usd=cost_usd,
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
