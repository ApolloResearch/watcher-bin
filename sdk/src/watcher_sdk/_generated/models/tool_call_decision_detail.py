from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Self, TypeVar, cast
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.applied_decision import AppliedDecision
from ..models.bypass_reason import BypassReason
from ..models.decided_by import DecidedBy
from ..models.decision_source import DecisionSource
from ..models.enforcement_mode import EnforcementMode
from ..models.human_decision import HumanDecision
from ..models.judged_decision import JudgedDecision
from ..models.policy_decision import PolicyDecision
from ..models.tool_call_decision_detail_ingest_kind_type_0 import (
    ToolCallDecisionDetailIngestKindType0,
)
from ..models.tool_status import ToolStatus
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.tool_call_decision_detail_raw_tool_call import (
        ToolCallDecisionDetailRawToolCall,
    )
    from ..models.tool_call_grade_detail import ToolCallGradeDetail


T = TypeVar("T", bound="ToolCallDecisionDetail")


@_attrs_define
class ToolCallDecisionDetail:
    """Persisted decision for one ingested tool call.

    Grade scores, models, and per-run provenance live in the nested ``grades``
    rows. Callers can select a grade by ``run_kind`` and read that row's grade
    payload.

        Attributes:
            tool_use_id (str):
            tool_name (str):
            raw_tool_call (ToolCallDecisionDetailRawToolCall):
            policy_decision (PolicyDecision): Superseded applied-decision vocabulary.

                ``AppliedDecision`` replaces this enum: it adds ``deferred`` so the server can
                tell "Watcher deliberately stood aside" apart from "never routed". This enum
                and the ``policy_decision`` field remain so clients and servers on either
                side of that change interoperate; new clients should read ``applied_decision``.
            tool_status (ToolStatus): Final execution status of the tool call.
            decision_source (DecisionSource): Subsystem that produced the policy decision.
            tool_call_id (UUID):
            tool_call_decision_id (UUID):
            tool_call_created_at (datetime.datetime):
            created_at (datetime.datetime):
            updated_at (datetime.datetime):
            latency_ms (float | None | Unset):
            flag_threshold (int | None | Unset):
            deny_threshold (int | None | Unset):
            triage_max_allow_score (int | None | Unset):
            rule_label (None | str | Unset):
            rule_pattern (None | str | Unset):
            summary (None | str | Unset):
            decision_context (None | str | Unset):
            human_decision (HumanDecision | None | Unset):
            human_decided_at (datetime.datetime | None | Unset):
            decided_by (DecidedBy | None | Unset): Who settled the call after Watcher handed it on: `person` (a person
                answered the permission prompt), `agent_review` (the agent's automated approval reviewer answered it, so there
                is no `human_decision` and `tool_status` holds the outcome) or `interrupt` (the person interrupted the turn
                before the call was answered, including while Watcher was still reviewing it). Null when the call is unsettled
                or the sender does not know who answered. Meaningful for escalations; other decisions may carry a value beside
                Watcher's own verdict.
            decided_at (datetime.datetime | None | Unset):
            applied_decision (AppliedDecision | None | Unset):
            judged_decision (JudgedDecision | None | Unset):
            enforcement_mode (EnforcementMode | None | Unset):
            bypass_reason (BypassReason | None | Unset):
            ingest_kind (None | ToolCallDecisionDetailIngestKindType0 | Unset): Delivery path of the current evaluation.
                Null means the path was not recorded; unknown stored values report other. Outcome-only updates preserve this
                attribution.
            api_key_id (None | str | Unset): ID of the API key that authenticated the current evaluation.
            api_key_name (None | str | Unset): API key name at the time of the current evaluation.
            grades (list[ToolCallGradeDetail] | Unset):
    """

    tool_use_id: str
    tool_name: str
    raw_tool_call: ToolCallDecisionDetailRawToolCall
    policy_decision: PolicyDecision
    tool_status: ToolStatus
    decision_source: DecisionSource
    tool_call_id: UUID
    tool_call_decision_id: UUID
    tool_call_created_at: datetime.datetime
    created_at: datetime.datetime
    updated_at: datetime.datetime
    latency_ms: float | None | Unset = UNSET
    flag_threshold: int | None | Unset = UNSET
    deny_threshold: int | None | Unset = UNSET
    triage_max_allow_score: int | None | Unset = UNSET
    rule_label: None | str | Unset = UNSET
    rule_pattern: None | str | Unset = UNSET
    summary: None | str | Unset = UNSET
    decision_context: None | str | Unset = UNSET
    human_decision: HumanDecision | None | Unset = UNSET
    human_decided_at: datetime.datetime | None | Unset = UNSET
    decided_by: DecidedBy | None | Unset = UNSET
    decided_at: datetime.datetime | None | Unset = UNSET
    applied_decision: AppliedDecision | None | Unset = UNSET
    judged_decision: JudgedDecision | None | Unset = UNSET
    enforcement_mode: EnforcementMode | None | Unset = UNSET
    bypass_reason: BypassReason | None | Unset = UNSET
    ingest_kind: None | ToolCallDecisionDetailIngestKindType0 | Unset = UNSET
    api_key_id: None | str | Unset = UNSET
    api_key_name: None | str | Unset = UNSET
    grades: list[ToolCallGradeDetail] | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        tool_use_id = self.tool_use_id

        tool_name = self.tool_name

        raw_tool_call = self.raw_tool_call.to_dict()

        policy_decision = self.policy_decision.value

        tool_status = self.tool_status.value

        decision_source = self.decision_source.value

        tool_call_id = str(self.tool_call_id)

        tool_call_decision_id = str(self.tool_call_decision_id)

        tool_call_created_at = self.tool_call_created_at.isoformat()

        created_at = self.created_at.isoformat()

        updated_at = self.updated_at.isoformat()

        latency_ms: float | None | Unset
        if isinstance(self.latency_ms, Unset):
            latency_ms = UNSET
        else:
            latency_ms = self.latency_ms

        flag_threshold: int | None | Unset
        if isinstance(self.flag_threshold, Unset):
            flag_threshold = UNSET
        else:
            flag_threshold = self.flag_threshold

        deny_threshold: int | None | Unset
        if isinstance(self.deny_threshold, Unset):
            deny_threshold = UNSET
        else:
            deny_threshold = self.deny_threshold

        triage_max_allow_score: int | None | Unset
        if isinstance(self.triage_max_allow_score, Unset):
            triage_max_allow_score = UNSET
        else:
            triage_max_allow_score = self.triage_max_allow_score

        rule_label: None | str | Unset
        if isinstance(self.rule_label, Unset):
            rule_label = UNSET
        else:
            rule_label = self.rule_label

        rule_pattern: None | str | Unset
        if isinstance(self.rule_pattern, Unset):
            rule_pattern = UNSET
        else:
            rule_pattern = self.rule_pattern

        summary: None | str | Unset
        if isinstance(self.summary, Unset):
            summary = UNSET
        else:
            summary = self.summary

        decision_context: None | str | Unset
        if isinstance(self.decision_context, Unset):
            decision_context = UNSET
        else:
            decision_context = self.decision_context

        human_decision: None | str | Unset
        if isinstance(self.human_decision, Unset):
            human_decision = UNSET
        elif isinstance(self.human_decision, HumanDecision):
            human_decision = self.human_decision.value
        else:
            human_decision = self.human_decision

        human_decided_at: None | str | Unset
        if isinstance(self.human_decided_at, Unset):
            human_decided_at = UNSET
        elif isinstance(self.human_decided_at, datetime.datetime):
            human_decided_at = self.human_decided_at.isoformat()
        else:
            human_decided_at = self.human_decided_at

        decided_by: None | str | Unset
        if isinstance(self.decided_by, Unset):
            decided_by = UNSET
        elif isinstance(self.decided_by, DecidedBy):
            decided_by = self.decided_by.value
        else:
            decided_by = self.decided_by

        decided_at: None | str | Unset
        if isinstance(self.decided_at, Unset):
            decided_at = UNSET
        elif isinstance(self.decided_at, datetime.datetime):
            decided_at = self.decided_at.isoformat()
        else:
            decided_at = self.decided_at

        applied_decision: None | str | Unset
        if isinstance(self.applied_decision, Unset):
            applied_decision = UNSET
        elif isinstance(self.applied_decision, AppliedDecision):
            applied_decision = self.applied_decision.value
        else:
            applied_decision = self.applied_decision

        judged_decision: None | str | Unset
        if isinstance(self.judged_decision, Unset):
            judged_decision = UNSET
        elif isinstance(self.judged_decision, JudgedDecision):
            judged_decision = self.judged_decision.value
        else:
            judged_decision = self.judged_decision

        enforcement_mode: None | str | Unset
        if isinstance(self.enforcement_mode, Unset):
            enforcement_mode = UNSET
        elif isinstance(self.enforcement_mode, EnforcementMode):
            enforcement_mode = self.enforcement_mode.value
        else:
            enforcement_mode = self.enforcement_mode

        bypass_reason: None | str | Unset
        if isinstance(self.bypass_reason, Unset):
            bypass_reason = UNSET
        elif isinstance(self.bypass_reason, BypassReason):
            bypass_reason = self.bypass_reason.value
        else:
            bypass_reason = self.bypass_reason

        ingest_kind: None | str | Unset
        if isinstance(self.ingest_kind, Unset):
            ingest_kind = UNSET
        elif isinstance(self.ingest_kind, ToolCallDecisionDetailIngestKindType0):
            ingest_kind = self.ingest_kind.value
        else:
            ingest_kind = self.ingest_kind

        api_key_id: None | str | Unset
        if isinstance(self.api_key_id, Unset):
            api_key_id = UNSET
        else:
            api_key_id = self.api_key_id

        api_key_name: None | str | Unset
        if isinstance(self.api_key_name, Unset):
            api_key_name = UNSET
        else:
            api_key_name = self.api_key_name

        grades: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.grades, Unset):
            grades = []
            for grades_item_data in self.grades:
                grades_item = grades_item_data.to_dict()
                grades.append(grades_item)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "tool_use_id": tool_use_id,
                "tool_name": tool_name,
                "raw_tool_call": raw_tool_call,
                "policy_decision": policy_decision,
                "tool_status": tool_status,
                "decision_source": decision_source,
                "tool_call_id": tool_call_id,
                "tool_call_decision_id": tool_call_decision_id,
                "tool_call_created_at": tool_call_created_at,
                "created_at": created_at,
                "updated_at": updated_at,
            }
        )
        if latency_ms is not UNSET:
            field_dict["latency_ms"] = latency_ms
        if flag_threshold is not UNSET:
            field_dict["flag_threshold"] = flag_threshold
        if deny_threshold is not UNSET:
            field_dict["deny_threshold"] = deny_threshold
        if triage_max_allow_score is not UNSET:
            field_dict["triage_max_allow_score"] = triage_max_allow_score
        if rule_label is not UNSET:
            field_dict["rule_label"] = rule_label
        if rule_pattern is not UNSET:
            field_dict["rule_pattern"] = rule_pattern
        if summary is not UNSET:
            field_dict["summary"] = summary
        if decision_context is not UNSET:
            field_dict["decision_context"] = decision_context
        if human_decision is not UNSET:
            field_dict["human_decision"] = human_decision
        if human_decided_at is not UNSET:
            field_dict["human_decided_at"] = human_decided_at
        if decided_by is not UNSET:
            field_dict["decided_by"] = decided_by
        if decided_at is not UNSET:
            field_dict["decided_at"] = decided_at
        if applied_decision is not UNSET:
            field_dict["applied_decision"] = applied_decision
        if judged_decision is not UNSET:
            field_dict["judged_decision"] = judged_decision
        if enforcement_mode is not UNSET:
            field_dict["enforcement_mode"] = enforcement_mode
        if bypass_reason is not UNSET:
            field_dict["bypass_reason"] = bypass_reason
        if ingest_kind is not UNSET:
            field_dict["ingest_kind"] = ingest_kind
        if api_key_id is not UNSET:
            field_dict["api_key_id"] = api_key_id
        if api_key_name is not UNSET:
            field_dict["api_key_name"] = api_key_name
        if grades is not UNSET:
            field_dict["grades"] = grades

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        from ..models.tool_call_decision_detail_raw_tool_call import (
            ToolCallDecisionDetailRawToolCall,
        )
        from ..models.tool_call_grade_detail import ToolCallGradeDetail

        d = dict(src_dict)
        tool_use_id = d.pop("tool_use_id")

        tool_name = d.pop("tool_name")

        raw_tool_call = ToolCallDecisionDetailRawToolCall.from_dict(
            d.pop("raw_tool_call")
        )

        policy_decision = PolicyDecision(d.pop("policy_decision"))

        tool_status = ToolStatus(d.pop("tool_status"))

        decision_source = DecisionSource(d.pop("decision_source"))

        tool_call_id = UUID(d.pop("tool_call_id"))

        tool_call_decision_id = UUID(d.pop("tool_call_decision_id"))

        tool_call_created_at = datetime.datetime.fromisoformat(
            d.pop("tool_call_created_at")
        )

        created_at = datetime.datetime.fromisoformat(d.pop("created_at"))

        updated_at = datetime.datetime.fromisoformat(d.pop("updated_at"))

        def _parse_latency_ms(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        latency_ms = _parse_latency_ms(d.pop("latency_ms", UNSET))

        def _parse_flag_threshold(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        flag_threshold = _parse_flag_threshold(d.pop("flag_threshold", UNSET))

        def _parse_deny_threshold(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        deny_threshold = _parse_deny_threshold(d.pop("deny_threshold", UNSET))

        def _parse_triage_max_allow_score(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        triage_max_allow_score = _parse_triage_max_allow_score(
            d.pop("triage_max_allow_score", UNSET)
        )

        def _parse_rule_label(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        rule_label = _parse_rule_label(d.pop("rule_label", UNSET))

        def _parse_rule_pattern(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        rule_pattern = _parse_rule_pattern(d.pop("rule_pattern", UNSET))

        def _parse_summary(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        summary = _parse_summary(d.pop("summary", UNSET))

        def _parse_decision_context(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        decision_context = _parse_decision_context(d.pop("decision_context", UNSET))

        def _parse_human_decision(data: object) -> HumanDecision | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                human_decision_type_0 = HumanDecision(data)

                return human_decision_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(HumanDecision | None | Unset, data)

        human_decision = _parse_human_decision(d.pop("human_decision", UNSET))

        def _parse_human_decided_at(data: object) -> datetime.datetime | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                human_decided_at_type_0 = datetime.datetime.fromisoformat(data)

                return human_decided_at_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None | Unset, data)

        human_decided_at = _parse_human_decided_at(d.pop("human_decided_at", UNSET))

        def _parse_decided_by(data: object) -> DecidedBy | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                decided_by_type_0 = DecidedBy(data)

                return decided_by_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(DecidedBy | None | Unset, data)

        decided_by = _parse_decided_by(d.pop("decided_by", UNSET))

        def _parse_decided_at(data: object) -> datetime.datetime | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                decided_at_type_0 = datetime.datetime.fromisoformat(data)

                return decided_at_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None | Unset, data)

        decided_at = _parse_decided_at(d.pop("decided_at", UNSET))

        def _parse_applied_decision(data: object) -> AppliedDecision | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                applied_decision_type_0 = AppliedDecision(data)

                return applied_decision_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(AppliedDecision | None | Unset, data)

        applied_decision = _parse_applied_decision(d.pop("applied_decision", UNSET))

        def _parse_judged_decision(data: object) -> JudgedDecision | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                judged_decision_type_0 = JudgedDecision(data)

                return judged_decision_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(JudgedDecision | None | Unset, data)

        judged_decision = _parse_judged_decision(d.pop("judged_decision", UNSET))

        def _parse_enforcement_mode(data: object) -> EnforcementMode | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                enforcement_mode_type_0 = EnforcementMode(data)

                return enforcement_mode_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(EnforcementMode | None | Unset, data)

        enforcement_mode = _parse_enforcement_mode(d.pop("enforcement_mode", UNSET))

        def _parse_bypass_reason(data: object) -> BypassReason | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                bypass_reason_type_0 = BypassReason(data)

                return bypass_reason_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(BypassReason | None | Unset, data)

        bypass_reason = _parse_bypass_reason(d.pop("bypass_reason", UNSET))

        def _parse_ingest_kind(
            data: object,
        ) -> None | ToolCallDecisionDetailIngestKindType0 | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                ingest_kind_type_0 = ToolCallDecisionDetailIngestKindType0(data)

                return ingest_kind_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | ToolCallDecisionDetailIngestKindType0 | Unset, data)

        ingest_kind = _parse_ingest_kind(d.pop("ingest_kind", UNSET))

        def _parse_api_key_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        api_key_id = _parse_api_key_id(d.pop("api_key_id", UNSET))

        def _parse_api_key_name(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        api_key_name = _parse_api_key_name(d.pop("api_key_name", UNSET))

        _grades = d.pop("grades", UNSET)
        grades: list[ToolCallGradeDetail] | Unset = UNSET
        if _grades is not UNSET:
            grades = []
            for grades_item_data in _grades:
                grades_item = ToolCallGradeDetail.from_dict(grades_item_data)

                grades.append(grades_item)

        tool_call_decision_detail = cls(
            tool_use_id=tool_use_id,
            tool_name=tool_name,
            raw_tool_call=raw_tool_call,
            policy_decision=policy_decision,
            tool_status=tool_status,
            decision_source=decision_source,
            tool_call_id=tool_call_id,
            tool_call_decision_id=tool_call_decision_id,
            tool_call_created_at=tool_call_created_at,
            created_at=created_at,
            updated_at=updated_at,
            latency_ms=latency_ms,
            flag_threshold=flag_threshold,
            deny_threshold=deny_threshold,
            triage_max_allow_score=triage_max_allow_score,
            rule_label=rule_label,
            rule_pattern=rule_pattern,
            summary=summary,
            decision_context=decision_context,
            human_decision=human_decision,
            human_decided_at=human_decided_at,
            decided_by=decided_by,
            decided_at=decided_at,
            applied_decision=applied_decision,
            judged_decision=judged_decision,
            enforcement_mode=enforcement_mode,
            bypass_reason=bypass_reason,
            ingest_kind=ingest_kind,
            api_key_id=api_key_id,
            api_key_name=api_key_name,
            grades=grades,
        )

        tool_call_decision_detail.additional_properties = d
        return tool_call_decision_detail

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
