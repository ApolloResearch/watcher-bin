from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Self, TypeVar, cast
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.related_session_summary_deep_review_status_type_0 import (
    RelatedSessionSummaryDeepReviewStatusType0,
)
from ..types import UNSET, Unset

T = TypeVar("T", bound="RelatedSessionSummary")


@_attrs_define
class RelatedSessionSummary:
    """Navigation metadata for one independently authorized related session.

    Titles require ownership or blanket content access, as in session lists.
    can_read_content also includes temporary approvals for opening the session;
    those approvals do not expose navigation titles. Review fields require findings access.
    A null review status means findings are restricted, not an unreviewed session.
    Scrubbing removes transcripts but retains permitted summaries and findings.

        Attributes:
            session_id (UUID):
            is_content_scrubbed (bool):
            can_read_findings (bool):
            can_read_content (bool):
            title (None | str | Unset):
            deep_review_severity (int | None | Unset):
            deep_review_status (None | RelatedSessionSummaryDeepReviewStatusType0 | Unset):
    """

    session_id: UUID
    is_content_scrubbed: bool
    can_read_findings: bool
    can_read_content: bool
    title: None | str | Unset = UNSET
    deep_review_severity: int | None | Unset = UNSET
    deep_review_status: None | RelatedSessionSummaryDeepReviewStatusType0 | Unset = (
        UNSET
    )
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        session_id = str(self.session_id)

        is_content_scrubbed = self.is_content_scrubbed

        can_read_findings = self.can_read_findings

        can_read_content = self.can_read_content

        title: None | str | Unset
        if isinstance(self.title, Unset):
            title = UNSET
        else:
            title = self.title

        deep_review_severity: int | None | Unset
        if isinstance(self.deep_review_severity, Unset):
            deep_review_severity = UNSET
        else:
            deep_review_severity = self.deep_review_severity

        deep_review_status: None | str | Unset
        if isinstance(self.deep_review_status, Unset):
            deep_review_status = UNSET
        elif isinstance(
            self.deep_review_status, RelatedSessionSummaryDeepReviewStatusType0
        ):
            deep_review_status = self.deep_review_status.value
        else:
            deep_review_status = self.deep_review_status

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "session_id": session_id,
                "is_content_scrubbed": is_content_scrubbed,
                "can_read_findings": can_read_findings,
                "can_read_content": can_read_content,
            }
        )
        if title is not UNSET:
            field_dict["title"] = title
        if deep_review_severity is not UNSET:
            field_dict["deep_review_severity"] = deep_review_severity
        if deep_review_status is not UNSET:
            field_dict["deep_review_status"] = deep_review_status

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        d = dict(src_dict)
        session_id = UUID(d.pop("session_id"))

        is_content_scrubbed = d.pop("is_content_scrubbed")

        can_read_findings = d.pop("can_read_findings")

        can_read_content = d.pop("can_read_content")

        def _parse_title(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        title = _parse_title(d.pop("title", UNSET))

        def _parse_deep_review_severity(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        deep_review_severity = _parse_deep_review_severity(
            d.pop("deep_review_severity", UNSET)
        )

        def _parse_deep_review_status(
            data: object,
        ) -> None | RelatedSessionSummaryDeepReviewStatusType0 | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                deep_review_status_type_0 = RelatedSessionSummaryDeepReviewStatusType0(
                    data
                )

                return deep_review_status_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | RelatedSessionSummaryDeepReviewStatusType0 | Unset, data)

        deep_review_status = _parse_deep_review_status(
            d.pop("deep_review_status", UNSET)
        )

        related_session_summary = cls(
            session_id=session_id,
            is_content_scrubbed=is_content_scrubbed,
            can_read_findings=can_read_findings,
            can_read_content=can_read_content,
            title=title,
            deep_review_severity=deep_review_severity,
            deep_review_status=deep_review_status,
        )

        related_session_summary.additional_properties = d
        return related_session_summary

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
