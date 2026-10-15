from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from typing_extensions import Self

T = TypeVar("T", bound="UsageLimitsResponse")


@_attrs_define
class UsageLimitsResponse:
    """Current-month grading limit status from GET /v1/usage/limits.

    No dollar figures: an org over its dollar cap reports stopped with its call
    figures still under the limit.

        Attributes:
            grading_stopped (bool):
            resets_at (datetime.datetime): Midnight UTC on the first of next month, when the caps reset.
            calls_used (int): Error-free non-triage grader calls this period.
            call_limit (int | None): Null means unlimited.
    """

    grading_stopped: bool
    resets_at: datetime.datetime
    calls_used: int
    call_limit: int | None
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        grading_stopped = self.grading_stopped

        resets_at = self.resets_at.isoformat()

        calls_used = self.calls_used

        call_limit: int | None
        call_limit = self.call_limit

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "grading_stopped": grading_stopped,
                "resets_at": resets_at,
                "calls_used": calls_used,
                "call_limit": call_limit,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        d = dict(src_dict)
        grading_stopped = d.pop("grading_stopped")

        resets_at = datetime.datetime.fromisoformat(d.pop("resets_at"))

        calls_used = d.pop("calls_used")

        def _parse_call_limit(data: object) -> int | None:
            if data is None:
                return data
            return cast(int | None, data)

        call_limit = _parse_call_limit(d.pop("call_limit"))

        usage_limits_response = cls(
            grading_stopped=grading_stopped,
            resets_at=resets_at,
            calls_used=calls_used,
            call_limit=call_limit,
        )

        usage_limits_response.additional_properties = d
        return usage_limits_response

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
