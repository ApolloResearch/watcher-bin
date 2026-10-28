from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Self, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="PriorHumanDecision")


@_attrs_define
class PriorHumanDecision:
    """One recent human-reviewed decision on this session, as data.

    ``response`` is the human's verdict (e.g. ``allow``/``deny``);
    ``tool_input`` is the gated call's input as it was stored. The server
    renders the list into the monitor prompt's recent-decisions section,
    oldest first.

        Attributes:
            tool_name (str):
            response (str):
            summary (None | str | Unset):
            decision_score (float | None | Unset):
            tool_input (Any | Unset):
    """

    tool_name: str
    response: str
    summary: None | str | Unset = UNSET
    decision_score: float | None | Unset = UNSET
    tool_input: Any | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        tool_name = self.tool_name

        response = self.response

        summary: None | str | Unset
        if isinstance(self.summary, Unset):
            summary = UNSET
        else:
            summary = self.summary

        decision_score: float | None | Unset
        if isinstance(self.decision_score, Unset):
            decision_score = UNSET
        else:
            decision_score = self.decision_score

        tool_input = self.tool_input

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "tool_name": tool_name,
                "response": response,
            }
        )
        if summary is not UNSET:
            field_dict["summary"] = summary
        if decision_score is not UNSET:
            field_dict["decision_score"] = decision_score
        if tool_input is not UNSET:
            field_dict["tool_input"] = tool_input

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        d = dict(src_dict)
        tool_name = d.pop("tool_name")

        response = d.pop("response")

        def _parse_summary(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        summary = _parse_summary(d.pop("summary", UNSET))

        def _parse_decision_score(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        decision_score = _parse_decision_score(d.pop("decision_score", UNSET))

        tool_input = d.pop("tool_input", UNSET)

        prior_human_decision = cls(
            tool_name=tool_name,
            response=response,
            summary=summary,
            decision_score=decision_score,
            tool_input=tool_input,
        )

        prior_human_decision.additional_properties = d
        return prior_human_decision

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
