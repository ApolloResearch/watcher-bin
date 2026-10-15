from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from typing_extensions import Self

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.session_capture_counts import SessionCaptureCounts


T = TypeVar("T", bound="SessionAnalyticsSummary")


@_attrs_define
class SessionAnalyticsSummary:
    """Summary counts for session aggregates.

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

        Attributes:
            total_sessions (int):
            matching_sessions (int):
            active_users (int | Unset):  Default: 0.
            matching_users (int | Unset):  Default: 0.
            reviewed_sessions (int | Unset):  Default: 0.
            pending_sessions (int | Unset):  Default: 0.
            session_capture (None | SessionCaptureCounts | Unset):
            tool_calls_evaluated (int | Unset):  Default: 0.
            tool_calls_blocked (int | Unset):  Default: 0.
            tool_calls_would_be_blocked (int | Unset):  Default: 0.
            tool_calls_would_be_escalated (int | Unset):  Default: 0.
            tool_calls_human_allowed (int | Unset):  Default: 0.
            tool_calls_would_be_flagged (int | Unset):  Default: 0.
            tool_calls_cleared_automatically (int | Unset):  Default: 0.
    """

    total_sessions: int
    matching_sessions: int
    active_users: int | Unset = 0
    matching_users: int | Unset = 0
    reviewed_sessions: int | Unset = 0
    pending_sessions: int | Unset = 0
    session_capture: None | SessionCaptureCounts | Unset = UNSET
    tool_calls_evaluated: int | Unset = 0
    tool_calls_blocked: int | Unset = 0
    tool_calls_would_be_blocked: int | Unset = 0
    tool_calls_would_be_escalated: int | Unset = 0
    tool_calls_human_allowed: int | Unset = 0
    tool_calls_would_be_flagged: int | Unset = 0
    tool_calls_cleared_automatically: int | Unset = 0
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.session_capture_counts import (
            SessionCaptureCounts,
        )

        total_sessions = self.total_sessions

        matching_sessions = self.matching_sessions

        active_users = self.active_users

        matching_users = self.matching_users

        reviewed_sessions = self.reviewed_sessions

        pending_sessions = self.pending_sessions

        session_capture: dict[str, Any] | None | Unset
        if isinstance(self.session_capture, Unset):
            session_capture = UNSET
        elif isinstance(self.session_capture, SessionCaptureCounts):
            session_capture = self.session_capture.to_dict()
        else:
            session_capture = self.session_capture

        tool_calls_evaluated = self.tool_calls_evaluated

        tool_calls_blocked = self.tool_calls_blocked

        tool_calls_would_be_blocked = self.tool_calls_would_be_blocked

        tool_calls_would_be_escalated = self.tool_calls_would_be_escalated

        tool_calls_human_allowed = self.tool_calls_human_allowed

        tool_calls_would_be_flagged = self.tool_calls_would_be_flagged

        tool_calls_cleared_automatically = self.tool_calls_cleared_automatically

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "total_sessions": total_sessions,
                "matching_sessions": matching_sessions,
            }
        )
        if active_users is not UNSET:
            field_dict["active_users"] = active_users
        if matching_users is not UNSET:
            field_dict["matching_users"] = matching_users
        if reviewed_sessions is not UNSET:
            field_dict["reviewed_sessions"] = reviewed_sessions
        if pending_sessions is not UNSET:
            field_dict["pending_sessions"] = pending_sessions
        if session_capture is not UNSET:
            field_dict["session_capture"] = session_capture
        if tool_calls_evaluated is not UNSET:
            field_dict["tool_calls_evaluated"] = tool_calls_evaluated
        if tool_calls_blocked is not UNSET:
            field_dict["tool_calls_blocked"] = tool_calls_blocked
        if tool_calls_would_be_blocked is not UNSET:
            field_dict["tool_calls_would_be_blocked"] = tool_calls_would_be_blocked
        if tool_calls_would_be_escalated is not UNSET:
            field_dict["tool_calls_would_be_escalated"] = tool_calls_would_be_escalated
        if tool_calls_human_allowed is not UNSET:
            field_dict["tool_calls_human_allowed"] = tool_calls_human_allowed
        if tool_calls_would_be_flagged is not UNSET:
            field_dict["tool_calls_would_be_flagged"] = tool_calls_would_be_flagged
        if tool_calls_cleared_automatically is not UNSET:
            field_dict["tool_calls_cleared_automatically"] = (
                tool_calls_cleared_automatically
            )

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        from ..models.session_capture_counts import (
            SessionCaptureCounts,
        )

        d = dict(src_dict)
        total_sessions = d.pop("total_sessions")

        matching_sessions = d.pop("matching_sessions")

        active_users = d.pop("active_users", UNSET)

        matching_users = d.pop("matching_users", UNSET)

        reviewed_sessions = d.pop("reviewed_sessions", UNSET)

        pending_sessions = d.pop("pending_sessions", UNSET)

        def _parse_session_capture(data: object) -> None | SessionCaptureCounts | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                session_capture_type_0 = SessionCaptureCounts.from_dict(data)

                return session_capture_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | SessionCaptureCounts | Unset, data)

        session_capture = _parse_session_capture(d.pop("session_capture", UNSET))

        tool_calls_evaluated = d.pop("tool_calls_evaluated", UNSET)

        tool_calls_blocked = d.pop("tool_calls_blocked", UNSET)

        tool_calls_would_be_blocked = d.pop("tool_calls_would_be_blocked", UNSET)

        tool_calls_would_be_escalated = d.pop("tool_calls_would_be_escalated", UNSET)

        tool_calls_human_allowed = d.pop("tool_calls_human_allowed", UNSET)

        tool_calls_would_be_flagged = d.pop("tool_calls_would_be_flagged", UNSET)

        tool_calls_cleared_automatically = d.pop(
            "tool_calls_cleared_automatically", UNSET
        )

        session_analytics_summary = cls(
            total_sessions=total_sessions,
            matching_sessions=matching_sessions,
            active_users=active_users,
            matching_users=matching_users,
            reviewed_sessions=reviewed_sessions,
            pending_sessions=pending_sessions,
            session_capture=session_capture,
            tool_calls_evaluated=tool_calls_evaluated,
            tool_calls_blocked=tool_calls_blocked,
            tool_calls_would_be_blocked=tool_calls_would_be_blocked,
            tool_calls_would_be_escalated=tool_calls_would_be_escalated,
            tool_calls_human_allowed=tool_calls_human_allowed,
            tool_calls_would_be_flagged=tool_calls_would_be_flagged,
            tool_calls_cleared_automatically=tool_calls_cleared_automatically,
        )

        session_analytics_summary.additional_properties = d
        return session_analytics_summary

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
