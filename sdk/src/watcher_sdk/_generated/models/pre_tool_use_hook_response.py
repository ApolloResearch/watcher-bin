from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.applied_decision import AppliedDecision
from ..models.decision_source import DecisionSource
from ..models.enforcement_mode import EnforcementMode
from ..models.judged_decision import JudgedDecision
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.gateway_result import GatewayResult
    from ..models.grading_failure import GradingFailure
    from ..models.rule_match import RuleMatch
    from ..models.triage_result import TriageResult
    from ..models.verdict import Verdict


T = TypeVar("T", bound="PreToolUseHookResponse")


@_attrs_define
class PreToolUseHookResponse:
    """Response body for POST /v1/hooks/pre-tool-use.

    `decision` is what the caller should do; `judged_decision` is what the
    pipeline concluded before the org's enforcement posture was applied. The
    two differ when the posture withholds enforcement. An `observe` response
    retains the completed judgment and stage results with `decision=deferred`.
    `paused` returns an unjudged `deferred` response and only ingests the transcript.
    `escalate` means the call requires human approval before
    proceeding — a caller with no human in the loop should treat it per its own
    policy (typically block, with `verdict.explanation` as the reason).

    `decision_source` says which pipeline stage decided: `threshold`
    (terminal per-tool thresholds), `rule` (a command rule; see `rule`),
    `bypass` (the effective mode skipped all evaluation), `triage` (the fast monitor
    auto-allowed — or, in `triage_only` mode, declined to clear the call),
    `policy_gateway` (the authoritative grade), or `grading_error`
    (grading failed and the org's failure policy applied; see
    `grading_error`). Callers enforce `decision` and alert on
    `decision_source`: an `allow` from `grading_error` is the org's
    fail-open policy speaking, not a clearance. The thresholds the decision
    was judged against are the org's managed settings, not echoed here.

    `verdict` is the decision-level view — the score that drove the decision
    banded into a label (the gateway's for `policy_gateway`, triage's for
    `triage`; null for rule/threshold decisions, which carry no score) plus
    the summary and explanation to show. Completed stage results retain their
    scores and evidence, including when triage and gateway disagree. A completed
    failed grade has no score, but can still carry its persisted grade-row ID.
    `tool_call_grade_id` identifies a persisted row attachable to a later decision
    upload; ephemeral results have a null ID because no grade row is stored.
    A stage that has not completed when its wait expires has no result yet.

        Attributes:
            decision (AppliedDecision): What Watcher actually did about a tool call.

                ``DEFERRED`` means Watcher deliberately stood aside (grading skipped by a
                snooze/ignore bypass or admin pause, or a judgment observe mode withheld)
                and the host agent's own permission flow gated the call. ``NOT_EVALUATED``
                means the call was never routed through Watcher at all (e.g. Codex tools
                that bypass the PermissionRequest hook). Watcher live's local ``block``
                outcome folds into ``deny`` at upload — what Watcher *did* is deny — while
                the block flavor is preserved on the local row's judged value.
            decision_source (DecisionSource): Subsystem that produced the policy decision.
            enforcement_mode (EnforcementMode): Admin-set, machine-wide enforcement mode snapshot at decision time.

                Stamped on every decision row — including plain allows — so observe-mode
                would-be block rates have a queryable denominator. NULL only on rows
                uploaded by clients that predate the posture columns.
            verdict (Verdict): The decision-level view of why a call was decided, whichever stage decided it.

                What a caller shows or logs regardless of `decision_source`: the deciding
                stage's score banded into a label, and the summary and explanation chosen
                for the caller (a rule's label for rule decisions, fixed text for
                `grading_error` and `bypass`, the monitor's own text otherwise). The
                per-stage models on completed responses (`rule`, `triage`, `gateway`) are
                the evidence behind it and are null when that stage did not run. The score
                is null when no graded stage decided. Paused and unnamed calls have no
                stage results because they skip evaluation.
            latency_ms (float):
            tool_use_id (None | str | Unset): Echoes this input's tool_use_id, or null when omitted.
            judged_decision (JudgedDecision | None | Unset):
            rule (None | RuleMatch | Unset):
            triage (None | TriageResult | Unset):
            gateway (GatewayResult | None | Unset):
            grading_error (GradingFailure | None | Unset):
    """

    decision: AppliedDecision
    decision_source: DecisionSource
    enforcement_mode: EnforcementMode
    verdict: Verdict
    latency_ms: float
    tool_use_id: None | str | Unset = UNSET
    judged_decision: JudgedDecision | None | Unset = UNSET
    rule: None | RuleMatch | Unset = UNSET
    triage: None | TriageResult | Unset = UNSET
    gateway: GatewayResult | None | Unset = UNSET
    grading_error: GradingFailure | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.gateway_result import GatewayResult
        from ..models.grading_failure import GradingFailure
        from ..models.rule_match import RuleMatch
        from ..models.triage_result import TriageResult

        decision = self.decision.value

        decision_source = self.decision_source.value

        enforcement_mode = self.enforcement_mode.value

        verdict = self.verdict.to_dict()

        latency_ms = self.latency_ms

        tool_use_id: None | str | Unset
        if isinstance(self.tool_use_id, Unset):
            tool_use_id = UNSET
        else:
            tool_use_id = self.tool_use_id

        judged_decision: None | str | Unset
        if isinstance(self.judged_decision, Unset):
            judged_decision = UNSET
        elif isinstance(self.judged_decision, JudgedDecision):
            judged_decision = self.judged_decision.value
        else:
            judged_decision = self.judged_decision

        rule: dict[str, Any] | None | Unset
        if isinstance(self.rule, Unset):
            rule = UNSET
        elif isinstance(self.rule, RuleMatch):
            rule = self.rule.to_dict()
        else:
            rule = self.rule

        triage: dict[str, Any] | None | Unset
        if isinstance(self.triage, Unset):
            triage = UNSET
        elif isinstance(self.triage, TriageResult):
            triage = self.triage.to_dict()
        else:
            triage = self.triage

        gateway: dict[str, Any] | None | Unset
        if isinstance(self.gateway, Unset):
            gateway = UNSET
        elif isinstance(self.gateway, GatewayResult):
            gateway = self.gateway.to_dict()
        else:
            gateway = self.gateway

        grading_error: dict[str, Any] | None | Unset
        if isinstance(self.grading_error, Unset):
            grading_error = UNSET
        elif isinstance(self.grading_error, GradingFailure):
            grading_error = self.grading_error.to_dict()
        else:
            grading_error = self.grading_error

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "decision": decision,
                "decision_source": decision_source,
                "enforcement_mode": enforcement_mode,
                "verdict": verdict,
                "latency_ms": latency_ms,
            }
        )
        if tool_use_id is not UNSET:
            field_dict["tool_use_id"] = tool_use_id
        if judged_decision is not UNSET:
            field_dict["judged_decision"] = judged_decision
        if rule is not UNSET:
            field_dict["rule"] = rule
        if triage is not UNSET:
            field_dict["triage"] = triage
        if gateway is not UNSET:
            field_dict["gateway"] = gateway
        if grading_error is not UNSET:
            field_dict["grading_error"] = grading_error

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.gateway_result import GatewayResult
        from ..models.grading_failure import GradingFailure
        from ..models.rule_match import RuleMatch
        from ..models.triage_result import TriageResult
        from ..models.verdict import Verdict

        d = dict(src_dict)
        decision = AppliedDecision(d.pop("decision"))

        decision_source = DecisionSource(d.pop("decision_source"))

        enforcement_mode = EnforcementMode(d.pop("enforcement_mode"))

        verdict = Verdict.from_dict(d.pop("verdict"))

        latency_ms = d.pop("latency_ms")

        def _parse_tool_use_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        tool_use_id = _parse_tool_use_id(d.pop("tool_use_id", UNSET))

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

        def _parse_rule(data: object) -> None | RuleMatch | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                rule_type_0 = RuleMatch.from_dict(data)

                return rule_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | RuleMatch | Unset, data)

        rule = _parse_rule(d.pop("rule", UNSET))

        def _parse_triage(data: object) -> None | TriageResult | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                triage_type_0 = TriageResult.from_dict(data)

                return triage_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | TriageResult | Unset, data)

        triage = _parse_triage(d.pop("triage", UNSET))

        def _parse_gateway(data: object) -> GatewayResult | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                gateway_type_0 = GatewayResult.from_dict(data)

                return gateway_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(GatewayResult | None | Unset, data)

        gateway = _parse_gateway(d.pop("gateway", UNSET))

        def _parse_grading_error(data: object) -> GradingFailure | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                grading_error_type_0 = GradingFailure.from_dict(data)

                return grading_error_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(GradingFailure | None | Unset, data)

        grading_error = _parse_grading_error(d.pop("grading_error", UNSET))

        pre_tool_use_hook_response = cls(
            decision=decision,
            decision_source=decision_source,
            enforcement_mode=enforcement_mode,
            verdict=verdict,
            latency_ms=latency_ms,
            tool_use_id=tool_use_id,
            judged_decision=judged_decision,
            rule=rule,
            triage=triage,
            gateway=gateway,
            grading_error=grading_error,
        )

        pre_tool_use_hook_response.additional_properties = d
        return pre_tool_use_hook_response

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
