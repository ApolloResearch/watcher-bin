from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import (
    TYPE_CHECKING,
    Any,
    Literal,
    TypeVar,
    cast,
)
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from typing_extensions import Self

from ..models.scrubbed_session_detail_response_ingest_kinds_item import (
    ScrubbedSessionDetailResponseIngestKindsItem,
)
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.grade_result import GradeResult
    from ..models.related_session_summary import RelatedSessionSummary
    from ..models.scrubbed_session_detail_response_external_ids_type_0 import (
        ScrubbedSessionDetailResponseExternalIdsType0,
    )
    from ..models.scrubbed_session_detail_response_metadata_type_0 import (
        ScrubbedSessionDetailResponseMetadataType0,
    )
    from ..models.trajectory_summary import TrajectorySummary


T = TypeVar("T", bound="ScrubbedSessionDetailResponse")


@_attrs_define
class ScrubbedSessionDetailResponse:
    """Session detail retaining grades but no trajectory content.

    Attributes:
        session_id (str):
        can_read_findings (bool): Whether this caller may read this session's findings.
        can_read_content (bool): Whether this caller may read this session's content. Scrubbed messages remain
            unavailable.
        agent_platform (str): Reported coding agent. Retained SDK adapter identities can name the agent, including for
            historical sessions stored as 'other'. Reporting does not change the stored ingestion identity. Clients must
            tolerate additional platform strings.
        started_at (datetime.datetime):
        ended_at (datetime.datetime):
        message_count (int):
        created_at (datetime.datetime):
        retained_grades (list[GradeResult]):
        is_subagent (bool | Unset): Whether this session has a recorded parent relationship. Default: False.
        parent_session (None | RelatedSessionSummary | Unset): Immediate parent, omitted when unknown or inaccessible to
            this caller.
        user_id (None | Unset | UUID):
        user_first_name (None | str | Unset):
        user_last_name (None | str | Unset):
        user_email (None | str | Unset):
        external_ids (None | ScrubbedSessionDetailResponseExternalIdsType0 | Unset):
        metadata (None | ScrubbedSessionDetailResponseMetadataType0 | Unset):
        ingest_kinds (list[ScrubbedSessionDetailResponseIngestKindsItem] | Unset): Sorted distinct recorded delivery
            paths, including duplicate uploads. Empty means no recorded delivery history; unknown stored values report
            other.
        sources (list[str] | Unset): Distinct canonical ingestion sources among retained session messages, sorted; same
            values as ``SessionSummary.sources``. Empty for a scrubbed session, whose messages are gone.
        content_state (Literal['scrubbed'] | Unset):  Default: 'scrubbed'.
        is_content_scrubbed (bool | Unset):  Default: True.
        latest_trajectory_id (None | Unset):
        trajectories (list[TrajectorySummary] | Unset):
        grades (list[GradeResult] | Unset):
    """

    session_id: str
    can_read_findings: bool
    can_read_content: bool
    agent_platform: str
    started_at: datetime.datetime
    ended_at: datetime.datetime
    message_count: int
    created_at: datetime.datetime
    retained_grades: list[GradeResult]
    is_subagent: bool | Unset = False
    parent_session: None | RelatedSessionSummary | Unset = UNSET
    user_id: None | Unset | UUID = UNSET
    user_first_name: None | str | Unset = UNSET
    user_last_name: None | str | Unset = UNSET
    user_email: None | str | Unset = UNSET
    external_ids: None | ScrubbedSessionDetailResponseExternalIdsType0 | Unset = UNSET
    metadata: None | ScrubbedSessionDetailResponseMetadataType0 | Unset = UNSET
    ingest_kinds: list[ScrubbedSessionDetailResponseIngestKindsItem] | Unset = UNSET
    sources: list[str] | Unset = UNSET
    content_state: Literal["scrubbed"] | Unset = "scrubbed"
    is_content_scrubbed: bool | Unset = True
    latest_trajectory_id: None | Unset = UNSET
    trajectories: list[TrajectorySummary] | Unset = UNSET
    grades: list[GradeResult] | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.related_session_summary import RelatedSessionSummary
        from ..models.scrubbed_session_detail_response_external_ids_type_0 import (
            ScrubbedSessionDetailResponseExternalIdsType0,
        )
        from ..models.scrubbed_session_detail_response_metadata_type_0 import (
            ScrubbedSessionDetailResponseMetadataType0,
        )

        session_id = self.session_id

        can_read_findings = self.can_read_findings

        can_read_content = self.can_read_content

        agent_platform = self.agent_platform

        started_at = self.started_at.isoformat()

        ended_at = self.ended_at.isoformat()

        message_count = self.message_count

        created_at = self.created_at.isoformat()

        retained_grades = []
        for retained_grades_item_data in self.retained_grades:
            retained_grades_item = retained_grades_item_data.to_dict()
            retained_grades.append(retained_grades_item)

        is_subagent = self.is_subagent

        parent_session: dict[str, Any] | None | Unset
        if isinstance(self.parent_session, Unset):
            parent_session = UNSET
        elif isinstance(self.parent_session, RelatedSessionSummary):
            parent_session = self.parent_session.to_dict()
        else:
            parent_session = self.parent_session

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
        elif isinstance(
            self.external_ids, ScrubbedSessionDetailResponseExternalIdsType0
        ):
            external_ids = self.external_ids.to_dict()
        else:
            external_ids = self.external_ids

        metadata: dict[str, Any] | None | Unset
        if isinstance(self.metadata, Unset):
            metadata = UNSET
        elif isinstance(self.metadata, ScrubbedSessionDetailResponseMetadataType0):
            metadata = self.metadata.to_dict()
        else:
            metadata = self.metadata

        ingest_kinds: list[str] | Unset = UNSET
        if not isinstance(self.ingest_kinds, Unset):
            ingest_kinds = []
            for ingest_kinds_item_data in self.ingest_kinds:
                ingest_kinds_item = ingest_kinds_item_data.value
                ingest_kinds.append(ingest_kinds_item)

        sources: list[str] | Unset = UNSET
        if not isinstance(self.sources, Unset):
            sources = self.sources

        content_state = self.content_state

        is_content_scrubbed = self.is_content_scrubbed

        latest_trajectory_id = self.latest_trajectory_id

        trajectories: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.trajectories, Unset):
            trajectories = []
            for trajectories_item_data in self.trajectories:
                trajectories_item = trajectories_item_data.to_dict()
                trajectories.append(trajectories_item)

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
                "session_id": session_id,
                "can_read_findings": can_read_findings,
                "can_read_content": can_read_content,
                "agent_platform": agent_platform,
                "started_at": started_at,
                "ended_at": ended_at,
                "message_count": message_count,
                "created_at": created_at,
                "retained_grades": retained_grades,
            }
        )
        if is_subagent is not UNSET:
            field_dict["is_subagent"] = is_subagent
        if parent_session is not UNSET:
            field_dict["parent_session"] = parent_session
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
        if ingest_kinds is not UNSET:
            field_dict["ingest_kinds"] = ingest_kinds
        if sources is not UNSET:
            field_dict["sources"] = sources
        if content_state is not UNSET:
            field_dict["content_state"] = content_state
        if is_content_scrubbed is not UNSET:
            field_dict["is_content_scrubbed"] = is_content_scrubbed
        if latest_trajectory_id is not UNSET:
            field_dict["latest_trajectory_id"] = latest_trajectory_id
        if trajectories is not UNSET:
            field_dict["trajectories"] = trajectories
        if grades is not UNSET:
            field_dict["grades"] = grades

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        from ..models.grade_result import GradeResult
        from ..models.related_session_summary import (
            RelatedSessionSummary,
        )
        from ..models.scrubbed_session_detail_response_external_ids_type_0 import (
            ScrubbedSessionDetailResponseExternalIdsType0,
        )
        from ..models.scrubbed_session_detail_response_metadata_type_0 import (
            ScrubbedSessionDetailResponseMetadataType0,
        )
        from ..models.trajectory_summary import TrajectorySummary

        d = dict(src_dict)
        session_id = d.pop("session_id")

        can_read_findings = d.pop("can_read_findings")

        can_read_content = d.pop("can_read_content")

        agent_platform = d.pop("agent_platform")

        started_at = datetime.datetime.fromisoformat(d.pop("started_at"))

        ended_at = datetime.datetime.fromisoformat(d.pop("ended_at"))

        message_count = d.pop("message_count")

        created_at = datetime.datetime.fromisoformat(d.pop("created_at"))

        retained_grades = []
        _retained_grades = d.pop("retained_grades")
        for retained_grades_item_data in _retained_grades:
            retained_grades_item = GradeResult.from_dict(retained_grades_item_data)

            retained_grades.append(retained_grades_item)

        is_subagent = d.pop("is_subagent", UNSET)

        def _parse_parent_session(data: object) -> None | RelatedSessionSummary | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                parent_session_type_0 = RelatedSessionSummary.from_dict(data)

                return parent_session_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | RelatedSessionSummary | Unset, data)

        parent_session = _parse_parent_session(d.pop("parent_session", UNSET))

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
        ) -> None | ScrubbedSessionDetailResponseExternalIdsType0 | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                external_ids_type_0 = (
                    ScrubbedSessionDetailResponseExternalIdsType0.from_dict(data)
                )

                return external_ids_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(
                None | ScrubbedSessionDetailResponseExternalIdsType0 | Unset, data
            )

        external_ids = _parse_external_ids(d.pop("external_ids", UNSET))

        def _parse_metadata(
            data: object,
        ) -> None | ScrubbedSessionDetailResponseMetadataType0 | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                metadata_type_0 = ScrubbedSessionDetailResponseMetadataType0.from_dict(
                    data
                )

                return metadata_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | ScrubbedSessionDetailResponseMetadataType0 | Unset, data)

        metadata = _parse_metadata(d.pop("metadata", UNSET))

        _ingest_kinds = d.pop("ingest_kinds", UNSET)
        ingest_kinds: list[ScrubbedSessionDetailResponseIngestKindsItem] | Unset = UNSET
        if _ingest_kinds is not UNSET:
            ingest_kinds = []
            for ingest_kinds_item_data in _ingest_kinds:
                ingest_kinds_item = ScrubbedSessionDetailResponseIngestKindsItem(
                    ingest_kinds_item_data
                )

                ingest_kinds.append(ingest_kinds_item)

        sources = cast(list[str], d.pop("sources", UNSET))

        content_state = cast(Literal["scrubbed"] | Unset, d.pop("content_state", UNSET))
        if content_state != "scrubbed" and not isinstance(content_state, Unset):
            raise ValueError(
                f"content_state must match const 'scrubbed', got '{content_state}'"
            )

        is_content_scrubbed = d.pop("is_content_scrubbed", UNSET)

        latest_trajectory_id = d.pop("latest_trajectory_id", UNSET)

        _trajectories = d.pop("trajectories", UNSET)
        trajectories: list[TrajectorySummary] | Unset = UNSET
        if _trajectories is not UNSET:
            trajectories = []
            for trajectories_item_data in _trajectories:
                trajectories_item = TrajectorySummary.from_dict(trajectories_item_data)

                trajectories.append(trajectories_item)

        _grades = d.pop("grades", UNSET)
        grades: list[GradeResult] | Unset = UNSET
        if _grades is not UNSET:
            grades = []
            for grades_item_data in _grades:
                grades_item = GradeResult.from_dict(grades_item_data)

                grades.append(grades_item)

        scrubbed_session_detail_response = cls(
            session_id=session_id,
            can_read_findings=can_read_findings,
            can_read_content=can_read_content,
            agent_platform=agent_platform,
            started_at=started_at,
            ended_at=ended_at,
            message_count=message_count,
            created_at=created_at,
            retained_grades=retained_grades,
            is_subagent=is_subagent,
            parent_session=parent_session,
            user_id=user_id,
            user_first_name=user_first_name,
            user_last_name=user_last_name,
            user_email=user_email,
            external_ids=external_ids,
            metadata=metadata,
            ingest_kinds=ingest_kinds,
            sources=sources,
            content_state=content_state,
            is_content_scrubbed=is_content_scrubbed,
            latest_trajectory_id=latest_trajectory_id,
            trajectories=trajectories,
            grades=grades,
        )

        scrubbed_session_detail_response.additional_properties = d
        return scrubbed_session_detail_response

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
