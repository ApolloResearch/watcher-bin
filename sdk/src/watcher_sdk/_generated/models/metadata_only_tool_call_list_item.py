from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import (
    Any,
    Literal,
    Self,
    TypeVar,
    cast,
)
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.applied_decision import AppliedDecision
from ..models.enforcement_mode import EnforcementMode
from ..models.judged_decision import JudgedDecision
from ..models.metadata_only_tool_call_list_item_coverage_state import (
    MetadataOnlyToolCallListItemCoverageState,
)
from ..models.metadata_only_tool_call_list_item_decision_category_type_0 import (
    MetadataOnlyToolCallListItemDecisionCategoryType0,
)
from ..models.tool_call_skip_reason import ToolCallSkipReason
from ..types import UNSET, Unset

T = TypeVar("T", bound="MetadataOnlyToolCallListItem")


@_attrs_define
class MetadataOnlyToolCallListItem:
    """A call the Watcher client reported without content, whose transcript has not arrived.

    It has no message to link to. Once Watcher stores the message holding the
    call, the same call is listed as available.

        Attributes:
            tool_call_id (UUID):
            session_id (UUID):
            occurred_at (datetime.datetime):
            is_flagged (bool): Whether Watcher recorded a policy block or escalation, excluding grading failures.
            tool_use_id (str): Transcript-local identifier of the tool call.
            tool_name (str): The tool's name as the agent reported it.
            severity_score (int | None | Unset):
            coverage_state (MetadataOnlyToolCallListItemCoverageState | Unset):  Default:
                MetadataOnlyToolCallListItemCoverageState.DECIDED.
            decision_category (MetadataOnlyToolCallListItemDecisionCategoryType0 | None | Unset):
            applied_decision (AppliedDecision | None | Unset): Original permission action, independent of grading success.
            judged_decision (JudgedDecision | None | Unset): Original policy judgment, including a failure-policy fallback.
            enforcement_mode (EnforcementMode | None | Unset): Mode in which the original permission action was recorded.
            skip_reason (None | ToolCallSkipReason | Unset): Why the Watcher client observed the call but did not grade it,
                when it reported it as skipped.
            user_id (None | Unset | UUID):
            user_first_name (None | str | Unset):
            user_last_name (None | str | Unset):
            user_email (None | str | Unset):
            content_state (Literal['metadata_only'] | Unset):  Default: 'metadata_only'.
    """

    tool_call_id: UUID
    session_id: UUID
    occurred_at: datetime.datetime
    is_flagged: bool
    tool_use_id: str
    tool_name: str
    severity_score: int | None | Unset = UNSET
    coverage_state: MetadataOnlyToolCallListItemCoverageState | Unset = (
        MetadataOnlyToolCallListItemCoverageState.DECIDED
    )
    decision_category: (
        MetadataOnlyToolCallListItemDecisionCategoryType0 | None | Unset
    ) = UNSET
    applied_decision: AppliedDecision | None | Unset = UNSET
    judged_decision: JudgedDecision | None | Unset = UNSET
    enforcement_mode: EnforcementMode | None | Unset = UNSET
    skip_reason: None | ToolCallSkipReason | Unset = UNSET
    user_id: None | Unset | UUID = UNSET
    user_first_name: None | str | Unset = UNSET
    user_last_name: None | str | Unset = UNSET
    user_email: None | str | Unset = UNSET
    content_state: Literal["metadata_only"] | Unset = "metadata_only"
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        tool_call_id = str(self.tool_call_id)

        session_id = str(self.session_id)

        occurred_at = self.occurred_at.isoformat()

        is_flagged = self.is_flagged

        tool_use_id = self.tool_use_id

        tool_name = self.tool_name

        severity_score: int | None | Unset
        if isinstance(self.severity_score, Unset):
            severity_score = UNSET
        else:
            severity_score = self.severity_score

        coverage_state: str | Unset = UNSET
        if not isinstance(self.coverage_state, Unset):
            coverage_state = self.coverage_state.value

        decision_category: None | str | Unset
        if isinstance(self.decision_category, Unset):
            decision_category = UNSET
        elif isinstance(
            self.decision_category, MetadataOnlyToolCallListItemDecisionCategoryType0
        ):
            decision_category = self.decision_category.value
        else:
            decision_category = self.decision_category

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

        skip_reason: None | str | Unset
        if isinstance(self.skip_reason, Unset):
            skip_reason = UNSET
        elif isinstance(self.skip_reason, ToolCallSkipReason):
            skip_reason = self.skip_reason.value
        else:
            skip_reason = self.skip_reason

        user_id: None | str | Unset
        if isinstance(self.user_id, Unset):
            user_id = UNSET
        elif isinstance(self.user_id, UUID):
            user_id = str(self.user_id)
        else:
            user_id = self.user_id

        user_first_name: None | str | Unset
        if isinstance(self.user_first_name, Unset):
            user_first_name = UNSET
        else:
            user_first_name = self.user_first_name

        user_last_name: None | str | Unset
        if isinstance(self.user_last_name, Unset):
            user_last_name = UNSET
        else:
            user_last_name = self.user_last_name

        user_email: None | str | Unset
        if isinstance(self.user_email, Unset):
            user_email = UNSET
        else:
            user_email = self.user_email

        content_state = self.content_state

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "tool_call_id": tool_call_id,
                "session_id": session_id,
                "occurred_at": occurred_at,
                "is_flagged": is_flagged,
                "tool_use_id": tool_use_id,
                "tool_name": tool_name,
            }
        )
        if severity_score is not UNSET:
            field_dict["severity_score"] = severity_score
        if coverage_state is not UNSET:
            field_dict["coverage_state"] = coverage_state
        if decision_category is not UNSET:
            field_dict["decision_category"] = decision_category
        if applied_decision is not UNSET:
            field_dict["applied_decision"] = applied_decision
        if judged_decision is not UNSET:
            field_dict["judged_decision"] = judged_decision
        if enforcement_mode is not UNSET:
            field_dict["enforcement_mode"] = enforcement_mode
        if skip_reason is not UNSET:
            field_dict["skip_reason"] = skip_reason
        if user_id is not UNSET:
            field_dict["user_id"] = user_id
        if user_first_name is not UNSET:
            field_dict["user_first_name"] = user_first_name
        if user_last_name is not UNSET:
            field_dict["user_last_name"] = user_last_name
        if user_email is not UNSET:
            field_dict["user_email"] = user_email
        if content_state is not UNSET:
            field_dict["content_state"] = content_state

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        d = dict(src_dict)
        tool_call_id = UUID(d.pop("tool_call_id"))

        session_id = UUID(d.pop("session_id"))

        occurred_at = datetime.datetime.fromisoformat(d.pop("occurred_at"))

        is_flagged = d.pop("is_flagged")

        tool_use_id = d.pop("tool_use_id")

        tool_name = d.pop("tool_name")

        def _parse_severity_score(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        severity_score = _parse_severity_score(d.pop("severity_score", UNSET))

        _coverage_state = d.pop("coverage_state", UNSET)
        coverage_state: MetadataOnlyToolCallListItemCoverageState | Unset
        if isinstance(_coverage_state, Unset):
            coverage_state = UNSET
        else:
            coverage_state = MetadataOnlyToolCallListItemCoverageState(_coverage_state)

        def _parse_decision_category(
            data: object,
        ) -> MetadataOnlyToolCallListItemDecisionCategoryType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                decision_category_type_0 = (
                    MetadataOnlyToolCallListItemDecisionCategoryType0(data)
                )

                return decision_category_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(
                MetadataOnlyToolCallListItemDecisionCategoryType0 | None | Unset, data
            )

        decision_category = _parse_decision_category(d.pop("decision_category", UNSET))

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

        def _parse_skip_reason(data: object) -> None | ToolCallSkipReason | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                skip_reason_type_0 = ToolCallSkipReason(data)

                return skip_reason_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | ToolCallSkipReason | Unset, data)

        skip_reason = _parse_skip_reason(d.pop("skip_reason", UNSET))

        def _parse_user_id(data: object) -> None | Unset | UUID:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                user_id_type_0 = UUID(data)

                return user_id_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | Unset | UUID, data)

        user_id = _parse_user_id(d.pop("user_id", UNSET))

        def _parse_user_first_name(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        user_first_name = _parse_user_first_name(d.pop("user_first_name", UNSET))

        def _parse_user_last_name(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        user_last_name = _parse_user_last_name(d.pop("user_last_name", UNSET))

        def _parse_user_email(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        user_email = _parse_user_email(d.pop("user_email", UNSET))

        content_state = cast(
            Literal["metadata_only"] | Unset, d.pop("content_state", UNSET)
        )
        if content_state != "metadata_only" and not isinstance(content_state, Unset):
            raise ValueError(
                f"content_state must match const 'metadata_only', got '{content_state}'"
            )

        metadata_only_tool_call_list_item = cls(
            tool_call_id=tool_call_id,
            session_id=session_id,
            occurred_at=occurred_at,
            is_flagged=is_flagged,
            tool_use_id=tool_use_id,
            tool_name=tool_name,
            severity_score=severity_score,
            coverage_state=coverage_state,
            decision_category=decision_category,
            applied_decision=applied_decision,
            judged_decision=judged_decision,
            enforcement_mode=enforcement_mode,
            skip_reason=skip_reason,
            user_id=user_id,
            user_first_name=user_first_name,
            user_last_name=user_last_name,
            user_email=user_email,
            content_state=content_state,
        )

        metadata_only_tool_call_list_item.additional_properties = d
        return metadata_only_tool_call_list_item

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
