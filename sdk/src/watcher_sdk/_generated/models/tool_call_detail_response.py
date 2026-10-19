from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from typing_extensions import Self

if TYPE_CHECKING:
    from ..models.tool_call_decision_detail import ToolCallDecisionDetail
    from ..models.tool_call_detail_response_arguments_type_0 import (
        ToolCallDetailResponseArgumentsType0,
    )
    from ..models.tool_call_result import ToolCallResult


T = TypeVar("T", bound="ToolCallDetailResponse")


@_attrs_define
class ToolCallDetailResponse:
    """One call with independently authorized findings and content.

    Access flags distinguish restriction from missing data: arguments/results are
    null without content access to this call, and decision is null without findings
    access. The flagged-call grant permits content here without session-content access.
    A call may also have no recorded decision or result. Decision raw content and
    grader input messages stay empty; arguments are exposed only in their own field.
    has_result reports stored-result existence even when result is restricted.

        Attributes:
            tool_use_id (str):
            tool_name (str):
            occurred_at (datetime.datetime):
            is_flagged (bool | None): Whether Watcher recorded a policy block or escalation, excluding grading failures;
                null without findings access.
            can_read_findings (bool):
            can_read_content (bool):
            arguments (None | ToolCallDetailResponseArgumentsType0):
            has_result (bool):
            result (None | ToolCallResult):
            decision (None | ToolCallDecisionDetail):
    """

    tool_use_id: str
    tool_name: str
    occurred_at: datetime.datetime
    is_flagged: bool | None
    can_read_findings: bool
    can_read_content: bool
    arguments: None | ToolCallDetailResponseArgumentsType0
    has_result: bool
    result: None | ToolCallResult
    decision: None | ToolCallDecisionDetail
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.tool_call_decision_detail import (
            ToolCallDecisionDetail,
        )
        from ..models.tool_call_detail_response_arguments_type_0 import (
            ToolCallDetailResponseArgumentsType0,
        )
        from ..models.tool_call_result import ToolCallResult

        tool_use_id = self.tool_use_id

        tool_name = self.tool_name

        occurred_at = self.occurred_at.isoformat()

        is_flagged: bool | None
        is_flagged = self.is_flagged

        can_read_findings = self.can_read_findings

        can_read_content = self.can_read_content

        arguments: dict[str, Any] | None
        if isinstance(self.arguments, ToolCallDetailResponseArgumentsType0):
            arguments = self.arguments.to_dict()
        else:
            arguments = self.arguments

        has_result = self.has_result

        result: dict[str, Any] | None
        if isinstance(self.result, ToolCallResult):
            result = self.result.to_dict()
        else:
            result = self.result

        decision: dict[str, Any] | None
        if isinstance(self.decision, ToolCallDecisionDetail):
            decision = self.decision.to_dict()
        else:
            decision = self.decision

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "tool_use_id": tool_use_id,
                "tool_name": tool_name,
                "occurred_at": occurred_at,
                "is_flagged": is_flagged,
                "can_read_findings": can_read_findings,
                "can_read_content": can_read_content,
                "arguments": arguments,
                "has_result": has_result,
                "result": result,
                "decision": decision,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        from ..models.tool_call_decision_detail import (
            ToolCallDecisionDetail,
        )
        from ..models.tool_call_detail_response_arguments_type_0 import (
            ToolCallDetailResponseArgumentsType0,
        )
        from ..models.tool_call_result import ToolCallResult

        d = dict(src_dict)
        tool_use_id = d.pop("tool_use_id")

        tool_name = d.pop("tool_name")

        occurred_at = datetime.datetime.fromisoformat(d.pop("occurred_at"))

        def _parse_is_flagged(data: object) -> bool | None:
            if data is None:
                return data
            return cast(bool | None, data)

        is_flagged = _parse_is_flagged(d.pop("is_flagged"))

        can_read_findings = d.pop("can_read_findings")

        can_read_content = d.pop("can_read_content")

        def _parse_arguments(
            data: object,
        ) -> None | ToolCallDetailResponseArgumentsType0:
            if data is None:
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                arguments_type_0 = ToolCallDetailResponseArgumentsType0.from_dict(data)

                return arguments_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | ToolCallDetailResponseArgumentsType0, data)

        arguments = _parse_arguments(d.pop("arguments"))

        has_result = d.pop("has_result")

        def _parse_result(data: object) -> None | ToolCallResult:
            if data is None:
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                result_type_0 = ToolCallResult.from_dict(data)

                return result_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | ToolCallResult, data)

        result = _parse_result(d.pop("result"))

        def _parse_decision(data: object) -> None | ToolCallDecisionDetail:
            if data is None:
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                decision_type_0 = ToolCallDecisionDetail.from_dict(data)

                return decision_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | ToolCallDecisionDetail, data)

        decision = _parse_decision(d.pop("decision"))

        tool_call_detail_response = cls(
            tool_use_id=tool_use_id,
            tool_name=tool_name,
            occurred_at=occurred_at,
            is_flagged=is_flagged,
            can_read_findings=can_read_findings,
            can_read_content=can_read_content,
            arguments=arguments,
            has_result=has_result,
            result=result,
            decision=decision,
        )

        tool_call_detail_response.additional_properties = d
        return tool_call_detail_response

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
