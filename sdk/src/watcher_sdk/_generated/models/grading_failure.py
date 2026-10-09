from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.grading_failure_code import GradingFailureCode
from ..models.grading_failure_stage_type_0 import GradingFailureStageType0
from ..types import UNSET, Unset

T = TypeVar("T", bound="GradingFailure")


@_attrs_define
class GradingFailure:
    """Why a graded stage could not decide, when the org's failure policy answered instead.

    `code` is the stable vocabulary to branch and alert on — each value calls
    for a different remedy (a larger caller budget or `triage_only` for
    `timeout`, server capacity for `at_capacity`, a raised allowance for
    `allowance_exhausted`, an outage for `grader_failed` and `no_result`).
    `message` is human-readable and may change between releases. `stage` is
    the graded stage that failed, so a caller that pauses a failing stage
    (the Watcher client's gateway breaker) does not blame the gateway for a
    triage failure.

        Attributes:
            code (GradingFailureCode):
            message (str):
            stage (GradingFailureStageType0 | None | Unset):
    """

    code: GradingFailureCode
    message: str
    stage: GradingFailureStageType0 | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        code = self.code.value

        message = self.message

        stage: None | str | Unset
        if isinstance(self.stage, Unset):
            stage = UNSET
        elif isinstance(self.stage, GradingFailureStageType0):
            stage = self.stage.value
        else:
            stage = self.stage

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "code": code,
                "message": message,
            }
        )
        if stage is not UNSET:
            field_dict["stage"] = stage

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        code = GradingFailureCode(d.pop("code"))

        message = d.pop("message")

        def _parse_stage(data: object) -> GradingFailureStageType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                stage_type_0 = GradingFailureStageType0(data)

                return stage_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(GradingFailureStageType0 | None | Unset, data)

        stage = _parse_stage(d.pop("stage", UNSET))

        grading_failure = cls(
            code=code,
            message=message,
            stage=stage,
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
