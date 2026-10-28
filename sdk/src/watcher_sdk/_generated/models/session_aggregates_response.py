from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Self, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.session_aggregates_response_severity_threshold import (
    SessionAggregatesResponseSeverityThreshold,
)
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.session_analytics_summary import SessionAnalyticsSummary
    from ..models.session_analytics_trend_point import SessionAnalyticsTrendPoint


T = TypeVar("T", bound="SessionAggregatesResponse")


@_attrs_define
class SessionAggregatesResponse:
    """Aggregate session metrics in one response.

    Matching/critical counts and trends are driven by each session's newest
    deep-review ``severity`` (the same severity source as the session list),
    converted from the requested severity threshold to a score floor. Sessions
    awaiting a first review are not counted: this reports reviewed verdicts, so a
    growing review backlog shows up as a flat matching count rather than a
    speculative one.

        Attributes:
            severity_threshold (SessionAggregatesResponseSeverityThreshold):
            summary (SessionAnalyticsSummary): Summary counts for session aggregates.

                ``matching_sessions`` is a finding (reviews at or above the selected severity
                threshold); ``reviewed_sessions`` and ``pending_sessions`` are the coverage that
                finding rests on. Read together they separate "nothing dangerous happened" from
                "little has been reviewed yet", which ``matching_sessions / total_sessions``
                alone cannot distinguish.

                ``active_users`` counts distinct known owners of sessions in the window;
                ``matching_users`` narrows those owners to sessions that meet the selected
                severity threshold. Multiple matching sessions from one person count once,
                while sessions without an owner remain in the session counts but cannot
                contribute to either user count.

                ``pending_sessions`` is bounded by the reviewer's rolling lookback, so it counts
                only sessions still genuinely queued. That makes it a point-in-time level rather
                than a total accumulated over the window, and comparing it across periods is
                therefore not meaningful.
            trends (list[SessionAnalyticsTrendPoint]):
            enforcement_mode (None | str | Unset):
    """

    severity_threshold: SessionAggregatesResponseSeverityThreshold
    summary: SessionAnalyticsSummary
    trends: list[SessionAnalyticsTrendPoint]
    enforcement_mode: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        severity_threshold = self.severity_threshold.value

        summary = self.summary.to_dict()

        trends = []
        for trends_item_data in self.trends:
            trends_item = trends_item_data.to_dict()
            trends.append(trends_item)

        enforcement_mode: None | str | Unset
        if isinstance(self.enforcement_mode, Unset):
            enforcement_mode = UNSET
        else:
            enforcement_mode = self.enforcement_mode

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "severity_threshold": severity_threshold,
                "summary": summary,
                "trends": trends,
            }
        )
        if enforcement_mode is not UNSET:
            field_dict["enforcement_mode"] = enforcement_mode

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        from ..models.session_analytics_summary import SessionAnalyticsSummary
        from ..models.session_analytics_trend_point import SessionAnalyticsTrendPoint

        d = dict(src_dict)
        severity_threshold = SessionAggregatesResponseSeverityThreshold(
            d.pop("severity_threshold")
        )

        summary = SessionAnalyticsSummary.from_dict(d.pop("summary"))

        trends = []
        _trends = d.pop("trends")
        for trends_item_data in _trends:
            trends_item = SessionAnalyticsTrendPoint.from_dict(trends_item_data)

            trends.append(trends_item)

        def _parse_enforcement_mode(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        enforcement_mode = _parse_enforcement_mode(d.pop("enforcement_mode", UNSET))

        session_aggregates_response = cls(
            severity_threshold=severity_threshold,
            summary=summary,
            trends=trends,
            enforcement_mode=enforcement_mode,
        )

        session_aggregates_response.additional_properties = d
        return session_aggregates_response

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
