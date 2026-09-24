from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.grading_failure_code import GradingFailureCode

T = TypeVar("T", bound="GradingFailure")


@_attrs_define
class GradingFailure:
    """Why a graded stage could not decide, when the org's failure policy answered instead.

    `code` is the stable vocabulary to branch and alert on — each value calls
    for a different remedy (a larger caller budget or `triage_only` for
    `timeout`, server capacity for `at_capacity`, a raised allowance for
    `allowance_exhausted`, an outage for `grader_failed` and `no_result`).
    `message` is human-readable and may change between releases.

        Attributes:
            code (GradingFailureCode):
            message (str):
    """

    code: GradingFailureCode
    message: str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        code = self.code.value

        message = self.message

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "code": code,
                "message": message,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        code = GradingFailureCode(d.pop("code"))

        message = d.pop("message")

        grading_failure = cls(
            code=code,
            message=message,
        )

        grading_failure.additional_properties = d
        return grading_failure

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
