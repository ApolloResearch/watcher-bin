from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="Verdict")


@_attrs_define
class Verdict:
    """The decision-level view of why a call was decided, whichever stage decided it.

    What a caller shows or logs regardless of `decision_source`: the deciding
    stage's score banded into a label, and the summary and explanation chosen
    for the caller (a rule's label for rule decisions, fixed text for
    `grading_error` and `bypass`, the monitor's own text otherwise). The
    per-stage models on completed responses (`rule`, `triage`, `gateway`) are
    the evidence behind it and are null when that stage did not run. The score
    is null when no graded stage decided. Paused and unnamed calls have no
    stage results because they skip evaluation.

        Attributes:
            severity_score (float | None | Unset):
            severity_label (None | str | Unset):
            summary (None | str | Unset):
            explanation (None | str | Unset):
    """

    severity_score: float | None | Unset = UNSET
    severity_label: None | str | Unset = UNSET
    summary: None | str | Unset = UNSET
    explanation: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        severity_score: float | None | Unset
        if isinstance(self.severity_score, Unset):
            severity_score = UNSET
        else:
            severity_score = self.severity_score

        severity_label: None | str | Unset
        if isinstance(self.severity_label, Unset):
            severity_label = UNSET
        else:
            severity_label = self.severity_label

        summary: None | str | Unset
        if isinstance(self.summary, Unset):
            summary = UNSET
        else:
            summary = self.summary

        explanation: None | str | Unset
        if isinstance(self.explanation, Unset):
            explanation = UNSET
        else:
            explanation = self.explanation

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if severity_score is not UNSET:
            field_dict["severity_score"] = severity_score
        if severity_label is not UNSET:
            field_dict["severity_label"] = severity_label
        if summary is not UNSET:
            field_dict["summary"] = summary
        if explanation is not UNSET:
            field_dict["explanation"] = explanation

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)

        def _parse_severity_score(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        severity_score = _parse_severity_score(d.pop("severity_score", UNSET))

        def _parse_severity_label(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        severity_label = _parse_severity_label(d.pop("severity_label", UNSET))

        def _parse_summary(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        summary = _parse_summary(d.pop("summary", UNSET))

        def _parse_explanation(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        explanation = _parse_explanation(d.pop("explanation", UNSET))

        verdict = cls(
            severity_score=severity_score,
            severity_label=severity_label,
            summary=summary,
            explanation=explanation,
        )

        verdict.additional_properties = d
        return verdict

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
