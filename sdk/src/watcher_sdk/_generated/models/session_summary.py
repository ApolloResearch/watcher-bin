from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from typing_extensions import Self

from ..models.session_summary_deep_review_status import SessionSummaryDeepReviewStatus
from ..models.session_summary_ingest_kinds_item import SessionSummaryIngestKindsItem
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.grade_result import GradeResult
    from ..models.session_permission_decisions import SessionPermissionDecisions
    from ..models.session_summary_external_ids_type_0 import (
        SessionSummaryExternalIdsType0,
    )
    from ..models.session_summary_metadata_type_0 import SessionSummaryMetadataType0


T = TypeVar("T", bound="SessionSummary")


@_attrs_define
class SessionSummary:
    """Summary of a session for list responses.

    Attributes:
        session_id (str):
        agent_platform (str): Reported coding agent. Retained SDK adapter identities can name the agent, including for
            historical sessions stored as 'other'. Reporting does not change the stored ingestion identity. Clients must
            tolerate additional platform strings.
        trajectory_count (int):
        message_count (int):
        started_at (datetime.datetime):
        ended_at (datetime.datetime):
        is_subagent (bool | Unset): Whether this session has a recorded parent relationship. Default: False.
        is_content_scrubbed (bool | Unset):  Default: False.
        latest_trajectory_id (None | str | Unset):
        user_id (None | Unset | UUID):
        user_first_name (None | str | Unset):
        user_last_name (None | str | Unset):
        user_email (None | str | Unset):
        external_ids (None | SessionSummaryExternalIdsType0 | Unset):
        metadata (None | SessionSummaryMetadataType0 | Unset):
        grades (list[GradeResult] | None | Unset):
        max_score (int | None | Unset):
        max_gateway_score (int | None | Unset):
        deep_review_severity (int | None | Unset):
        deep_review_status (SessionSummaryDeepReviewStatus | Unset):  Default:
            SessionSummaryDeepReviewStatus.NOT_REVIEWED.
        deep_review_reviewed_at (datetime.datetime | None | Unset):
        permission_decisions (None | SessionPermissionDecisions | Unset):
        ingest_kinds (list[SessionSummaryIngestKindsItem] | Unset): Sorted distinct recorded delivery paths, including
            duplicate uploads. Empty means no recorded delivery history; unknown stored values report other.
        sources (list[str] | Unset): Distinct canonical ingestion sources among retained session messages, sorted. Known
            values: 'watcher' (Watcher Live upload), 'tailscale-aperture' (Aperture ingestion), and three keys for other
            hook ingest, including raw pre-tool-use captures, chosen by the session's retained 'other' conversation ID:
            'watcher-gateway' (a gateway integration's prefix, such as 'litellm:'), 'watcher-sdk' (a registered SDK agent's
            prefix, such as 'aider:'), and 'watcher-hook' (any other ID or none). Hook captures marked as Aperture, and
            legacy captures without a transport marker, are classified as 'tailscale-aperture'; other source keys pass
            through. Classification is for reporting only: stored message sources are unchanged. Empty for scrubbed sessions
            or sessions without stored messages. This is not a complete ingestion history.
    """

    session_id: str
    agent_platform: str
    trajectory_count: int
    message_count: int
    started_at: datetime.datetime
    ended_at: datetime.datetime
    is_subagent: bool | Unset = False
    is_content_scrubbed: bool | Unset = False
    latest_trajectory_id: None | str | Unset = UNSET
    user_id: None | Unset | UUID = UNSET
    user_first_name: None | str | Unset = UNSET
    user_last_name: None | str | Unset = UNSET
    user_email: None | str | Unset = UNSET
    external_ids: None | SessionSummaryExternalIdsType0 | Unset = UNSET
    metadata: None | SessionSummaryMetadataType0 | Unset = UNSET
    grades: list[GradeResult] | None | Unset = UNSET
    max_score: int | None | Unset = UNSET
    max_gateway_score: int | None | Unset = UNSET
    deep_review_severity: int | None | Unset = UNSET
    deep_review_status: SessionSummaryDeepReviewStatus | Unset = (
        SessionSummaryDeepReviewStatus.NOT_REVIEWED
    )
    deep_review_reviewed_at: datetime.datetime | None | Unset = UNSET
    permission_decisions: None | SessionPermissionDecisions | Unset = UNSET
    ingest_kinds: list[SessionSummaryIngestKindsItem] | Unset = UNSET
    sources: list[str] | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.session_permission_decisions import SessionPermissionDecisions
        from ..models.session_summary_external_ids_type_0 import (
            SessionSummaryExternalIdsType0,
        )
        from ..models.session_summary_metadata_type_0 import SessionSummaryMetadataType0

        session_id = self.session_id

        agent_platform = self.agent_platform

        trajectory_count = self.trajectory_count

        message_count = self.message_count

        started_at = self.started_at.isoformat()

        ended_at = self.ended_at.isoformat()

        is_subagent = self.is_subagent

        is_content_scrubbed = self.is_content_scrubbed

        latest_trajectory_id: None | str | Unset
        if isinstance(self.latest_trajectory_id, Unset):
            latest_trajectory_id = UNSET
        else:
            latest_trajectory_id = self.latest_trajectory_id

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

        external_ids: dict[str, Any] | None | Unset
        if isinstance(self.external_ids, Unset):
            external_ids = UNSET
        elif isinstance(self.external_ids, SessionSummaryExternalIdsType0):
            external_ids = self.external_ids.to_dict()
        else:
            external_ids = self.external_ids

        metadata: dict[str, Any] | None | Unset
        if isinstance(self.metadata, Unset):
            metadata = UNSET
        elif isinstance(self.metadata, SessionSummaryMetadataType0):
            metadata = self.metadata.to_dict()
        else:
            metadata = self.metadata

        grades: list[dict[str, Any]] | None | Unset
        if isinstance(self.grades, Unset):
            grades = UNSET
        elif isinstance(self.grades, list):
            grades = []
            for grades_type_0_item_data in self.grades:
                grades_type_0_item = grades_type_0_item_data.to_dict()
                grades.append(grades_type_0_item)

        else:
            grades = self.grades

        max_score: int | None | Unset
        if isinstance(self.max_score, Unset):
            max_score = UNSET
        else:
            max_score = self.max_score

        max_gateway_score: int | None | Unset
        if isinstance(self.max_gateway_score, Unset):
            max_gateway_score = UNSET
        else:
            max_gateway_score = self.max_gateway_score

        deep_review_severity: int | None | Unset
        if isinstance(self.deep_review_severity, Unset):
            deep_review_severity = UNSET
        else:
            deep_review_severity = self.deep_review_severity

        deep_review_status: str | Unset = UNSET
        if not isinstance(self.deep_review_status, Unset):
            deep_review_status = self.deep_review_status.value

        deep_review_reviewed_at: None | str | Unset
        if isinstance(self.deep_review_reviewed_at, Unset):
            deep_review_reviewed_at = UNSET
        elif isinstance(self.deep_review_reviewed_at, datetime.datetime):
            deep_review_reviewed_at = self.deep_review_reviewed_at.isoformat()
        else:
            deep_review_reviewed_at = self.deep_review_reviewed_at

        permission_decisions: dict[str, Any] | None | Unset
        if isinstance(self.permission_decisions, Unset):
            permission_decisions = UNSET
        elif isinstance(self.permission_decisions, SessionPermissionDecisions):
            permission_decisions = self.permission_decisions.to_dict()
        else:
            permission_decisions = self.permission_decisions

        ingest_kinds: list[str] | Unset = UNSET
        if not isinstance(self.ingest_kinds, Unset):
            ingest_kinds = []
            for ingest_kinds_item_data in self.ingest_kinds:
                ingest_kinds_item = ingest_kinds_item_data.value
                ingest_kinds.append(ingest_kinds_item)

        sources: list[str] | Unset = UNSET
        if not isinstance(self.sources, Unset):
            sources = self.sources

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "session_id": session_id,
                "agent_platform": agent_platform,
                "trajectory_count": trajectory_count,
                "message_count": message_count,
                "started_at": started_at,
                "ended_at": ended_at,
            }
        )
        if is_subagent is not UNSET:
            field_dict["is_subagent"] = is_subagent
        if is_content_scrubbed is not UNSET:
            field_dict["is_content_scrubbed"] = is_content_scrubbed
        if latest_trajectory_id is not UNSET:
            field_dict["latest_trajectory_id"] = latest_trajectory_id
        if user_id is not UNSET:
            field_dict["user_id"] = user_id
        if user_first_name is not UNSET:
            field_dict["user_first_name"] = user_first_name
        if user_last_name is not UNSET:
            field_dict["user_last_name"] = user_last_name
        if user_email is not UNSET:
            field_dict["user_email"] = user_email
        if external_ids is not UNSET:
            field_dict["external_ids"] = external_ids
        if metadata is not UNSET:
            field_dict["metadata"] = metadata
        if grades is not UNSET:
            field_dict["grades"] = grades
        if max_score is not UNSET:
            field_dict["max_score"] = max_score
        if max_gateway_score is not UNSET:
            field_dict["max_gateway_score"] = max_gateway_score
        if deep_review_severity is not UNSET:
            field_dict["deep_review_severity"] = deep_review_severity
        if deep_review_status is not UNSET:
            field_dict["deep_review_status"] = deep_review_status
        if deep_review_reviewed_at is not UNSET:
            field_dict["deep_review_reviewed_at"] = deep_review_reviewed_at
        if permission_decisions is not UNSET:
            field_dict["permission_decisions"] = permission_decisions
        if ingest_kinds is not UNSET:
            field_dict["ingest_kinds"] = ingest_kinds
        if sources is not UNSET:
            field_dict["sources"] = sources

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        from ..models.grade_result import GradeResult
        from ..models.session_permission_decisions import (
            SessionPermissionDecisions,
        )
        from ..models.session_summary_external_ids_type_0 import (
            SessionSummaryExternalIdsType0,
        )
        from ..models.session_summary_metadata_type_0 import (
            SessionSummaryMetadataType0,
        )

        d = dict(src_dict)
        session_id = d.pop("session_id")

        agent_platform = d.pop("agent_platform")

        trajectory_count = d.pop("trajectory_count")

        message_count = d.pop("message_count")

        started_at = datetime.datetime.fromisoformat(d.pop("started_at"))

        ended_at = datetime.datetime.fromisoformat(d.pop("ended_at"))

        is_subagent = d.pop("is_subagent", UNSET)

        is_content_scrubbed = d.pop("is_content_scrubbed", UNSET)

        def _parse_latest_trajectory_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        latest_trajectory_id = _parse_latest_trajectory_id(
            d.pop("latest_trajectory_id", UNSET)
        )

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

        def _parse_external_ids(
            data: object,
        ) -> None | SessionSummaryExternalIdsType0 | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                external_ids_type_0 = SessionSummaryExternalIdsType0.from_dict(data)

                return external_ids_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | SessionSummaryExternalIdsType0 | Unset, data)

        external_ids = _parse_external_ids(d.pop("external_ids", UNSET))

        def _parse_metadata(data: object) -> None | SessionSummaryMetadataType0 | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                metadata_type_0 = SessionSummaryMetadataType0.from_dict(data)

                return metadata_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | SessionSummaryMetadataType0 | Unset, data)

        metadata = _parse_metadata(d.pop("metadata", UNSET))

        def _parse_grades(data: object) -> list[GradeResult] | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                grades_type_0 = []
                _grades_type_0 = data
                for grades_type_0_item_data in _grades_type_0:
                    grades_type_0_item = GradeResult.from_dict(grades_type_0_item_data)

                    grades_type_0.append(grades_type_0_item)

                return grades_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(list[GradeResult] | None | Unset, data)

        grades = _parse_grades(d.pop("grades", UNSET))

        def _parse_max_score(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        max_score = _parse_max_score(d.pop("max_score", UNSET))

        def _parse_max_gateway_score(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        max_gateway_score = _parse_max_gateway_score(d.pop("max_gateway_score", UNSET))

        def _parse_deep_review_severity(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        deep_review_severity = _parse_deep_review_severity(
            d.pop("deep_review_severity", UNSET)
        )

        _deep_review_status = d.pop("deep_review_status", UNSET)
        deep_review_status: SessionSummaryDeepReviewStatus | Unset
        if isinstance(_deep_review_status, Unset):
            deep_review_status = UNSET
        else:
            deep_review_status = SessionSummaryDeepReviewStatus(_deep_review_status)

        def _parse_deep_review_reviewed_at(
            data: object,
        ) -> datetime.datetime | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                deep_review_reviewed_at_type_0 = datetime.datetime.fromisoformat(data)

                return deep_review_reviewed_at_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None | Unset, data)

        deep_review_reviewed_at = _parse_deep_review_reviewed_at(
            d.pop("deep_review_reviewed_at", UNSET)
        )

        def _parse_permission_decisions(
            data: object,
        ) -> None | SessionPermissionDecisions | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                permission_decisions_type_0 = SessionPermissionDecisions.from_dict(data)

                return permission_decisions_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | SessionPermissionDecisions | Unset, data)

        permission_decisions = _parse_permission_decisions(
            d.pop("permission_decisions", UNSET)
        )

        _ingest_kinds = d.pop("ingest_kinds", UNSET)
        ingest_kinds: list[SessionSummaryIngestKindsItem] | Unset = UNSET
        if _ingest_kinds is not UNSET:
            ingest_kinds = []
            for ingest_kinds_item_data in _ingest_kinds:
                ingest_kinds_item = SessionSummaryIngestKindsItem(
                    ingest_kinds_item_data
                )

                ingest_kinds.append(ingest_kinds_item)

        sources = cast(list[str], d.pop("sources", UNSET))

        session_summary = cls(
            session_id=session_id,
            agent_platform=agent_platform,
            trajectory_count=trajectory_count,
            message_count=message_count,
            started_at=started_at,
            ended_at=ended_at,
            is_subagent=is_subagent,
            is_content_scrubbed=is_content_scrubbed,
            latest_trajectory_id=latest_trajectory_id,
            user_id=user_id,
            user_first_name=user_first_name,
            user_last_name=user_last_name,
            user_email=user_email,
            external_ids=external_ids,
            metadata=metadata,
            grades=grades,
            max_score=max_score,
            max_gateway_score=max_gateway_score,
            deep_review_severity=deep_review_severity,
            deep_review_status=deep_review_status,
            deep_review_reviewed_at=deep_review_reviewed_at,
            permission_decisions=permission_decisions,
            ingest_kinds=ingest_kinds,
            sources=sources,
        )

        session_summary.additional_properties = d
        return session_summary

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
