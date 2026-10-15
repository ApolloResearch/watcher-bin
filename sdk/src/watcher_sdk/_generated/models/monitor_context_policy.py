from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from typing_extensions import Self

T = TypeVar("T", bound="MonitorContextPolicy")


@_attrs_define
class MonitorContextPolicy:
    """What of the transcript enters a client-invoked monitor's prompt.

    Server-owned counterparts of the ``policy_monitors`` client settings: a
    client grading by role applies these values instead of its local settings,
    so changing what the monitors see becomes a registry edit rather than a
    client release. Field semantics match the ``policy_monitors`` section of
    the client settings schema.

        Attributes:
            context_user_messages (int | str): A positive count of recent user messages, or 'all' for the whole transcript.
            include_tool_outputs (bool):
            include_agent_reasoning (bool):
            include_triage_assessment (bool):
            triage_max_allow_score (int):
    """

    context_user_messages: int | str
    include_tool_outputs: bool
    include_agent_reasoning: bool
    include_triage_assessment: bool
    triage_max_allow_score: int
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        context_user_messages: int | str
        context_user_messages = self.context_user_messages

        include_tool_outputs = self.include_tool_outputs

        include_agent_reasoning = self.include_agent_reasoning

        include_triage_assessment = self.include_triage_assessment

        triage_max_allow_score = self.triage_max_allow_score

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "context_user_messages": context_user_messages,
                "include_tool_outputs": include_tool_outputs,
                "include_agent_reasoning": include_agent_reasoning,
                "include_triage_assessment": include_triage_assessment,
                "triage_max_allow_score": triage_max_allow_score,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        d = dict(src_dict)

        def _parse_context_user_messages(data: object) -> int | str:
            return cast(int | str, data)

        context_user_messages = _parse_context_user_messages(
            d.pop("context_user_messages")
        )

        include_tool_outputs = d.pop("include_tool_outputs")

        include_agent_reasoning = d.pop("include_agent_reasoning")

        include_triage_assessment = d.pop("include_triage_assessment")

        triage_max_allow_score = d.pop("triage_max_allow_score")

        monitor_context_policy = cls(
            context_user_messages=context_user_messages,
            include_tool_outputs=include_tool_outputs,
            include_agent_reasoning=include_agent_reasoning,
            include_triage_assessment=include_triage_assessment,
            triage_max_allow_score=triage_max_allow_score,
        )

        monitor_context_policy.additional_properties = d
        return monitor_context_policy

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
