from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Self, TypeVar, cast
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="TriageResult")


@_attrs_define
class TriageResult:
    """The triage monitor's verdict on the gated call.

    Attributes:
        score (float | None | Unset):
        tool_call_grade_id (None | Unset | UUID):
        summary (None | str | Unset):
    """

    score: float | None | Unset = UNSET
    tool_call_grade_id: None | Unset | UUID = UNSET
    summary: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        score: float | None | Unset
        if isinstance(self.score, Unset):
            score = UNSET
        else:
            score = self.score

        tool_call_grade_id: None | str | Unset
        if isinstance(self.tool_call_grade_id, Unset):
            tool_call_grade_id = UNSET
        elif isinstance(self.tool_call_grade_id, UUID):
            tool_call_grade_id = str(self.tool_call_grade_id)
        else:
            tool_call_grade_id = self.tool_call_grade_id

        summary: None | str | Unset
        if isinstance(self.summary, Unset):
            summary = UNSET
        else:
            summary = self.summary

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if score is not UNSET:
            field_dict["score"] = score
        if tool_call_grade_id is not UNSET:
            field_dict["tool_call_grade_id"] = tool_call_grade_id
        if summary is not UNSET:
            field_dict["summary"] = summary

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        d = dict(src_dict)

        def _parse_score(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        score = _parse_score(d.pop("score", UNSET))

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

        def _parse_summary(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        summary = _parse_summary(d.pop("summary", UNSET))

        triage_result = cls(
            score=score,
            tool_call_grade_id=tool_call_grade_id,
            summary=summary,
        )

        triage_result.additional_properties = d
        return triage_result

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
