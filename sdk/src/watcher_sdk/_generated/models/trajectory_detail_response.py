from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Self, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.gateway_withheld_decision_detail import GatewayWithheldDecisionDetail
    from ..models.grade_result import GradeResult
    from ..models.spawned_subagent import SpawnedSubagent
    from ..models.trajectory_detail_response_messages_item import (
        TrajectoryDetailResponseMessagesItem,
    )
    from ..models.trajectory_detail_response_metadata import (
        TrajectoryDetailResponseMetadata,
    )
    from ..models.trajectory_detail_response_tool_call_decisions import (
        TrajectoryDetailResponseToolCallDecisions,
    )


T = TypeVar("T", bound="TrajectoryDetailResponse")


@_attrs_define
class TrajectoryDetailResponse:
    """Full trajectory detail from GET /v1/trajectories/{id} or /sessions/{sid}/trajectories/{tid}.

    Attributes:
        trajectory_id (str):
        messages (list[TrajectoryDetailResponseMessagesItem]):
        grades (list[GradeResult]):
        metadata (TrajectoryDetailResponseMetadata): The stored metadata of this transcript's own last stored message
            only, not combined across messages as the session's metadata is. For Claude Code, 'claude_code_entrypoint' and
            'claude_code_entry_version' come from the transcript entry that message came from. For Codex ('originator',
            'cli_version') and GitHub Copilot CLI ('cli_version') they are the session record's values copied onto every
            message of the upload, so they do not show which release wrote that message. The upload's own metadata, such as
            'hostname', is also included. Values can differ from the session's 'entrypoint' and 'agent_version' after a
            resume or an upgrade.
        session_id (str):
        source (str):
        created_at (datetime.datetime):
        tool_call_decisions (TrajectoryDetailResponseToolCallDecisions | Unset):
        gateway_withheld_decisions (list[GatewayWithheldDecisionDetail] | Unset): Decisions for calls a gateway withheld
            in favor of a message on this trajectory, as named by withheld_tool_use_ids on the raw-format hook request that
            recorded that message. A call is listed when it is stored in this session with a Watcher evaluation and this
            trajectory does not show it. Each entry's gateway_delivery names the delivered message it belongs before.
            Ordered by the proposing message's index, then its storage order (internal message ID), then the call's position
            in that message's tool calls, then tool-use ID. Empty without findings access.
        spawned_subagents (list[SpawnedSubagent] | Unset):
        member_trajectory_ids (list[str] | Unset): The stored trajectories this transcript covers, its own id first. A
            conversation recorded by both the Watcher client and a gateway is read as one transcript that lists both
            recordings here; any of these ids opens the same transcript. A single recording lists only its own id.
        transcript_revision (None | str | Unset): Revision of a transcript that reconciles two recordings; null for a
            single recording. A report whose grades.input_revision matches read exactly these messages, so its [M#]
            citations number them.
    """

    trajectory_id: str
    messages: list[TrajectoryDetailResponseMessagesItem]
    grades: list[GradeResult]
    metadata: TrajectoryDetailResponseMetadata
    session_id: str
    source: str
    created_at: datetime.datetime
    tool_call_decisions: TrajectoryDetailResponseToolCallDecisions | Unset = UNSET
    gateway_withheld_decisions: list[GatewayWithheldDecisionDetail] | Unset = UNSET
    spawned_subagents: list[SpawnedSubagent] | Unset = UNSET
    member_trajectory_ids: list[str] | Unset = UNSET
    transcript_revision: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        trajectory_id = self.trajectory_id

        messages = []
        for messages_item_data in self.messages:
            messages_item = messages_item_data.to_dict()
            messages.append(messages_item)

        grades = []
        for grades_item_data in self.grades:
            grades_item = grades_item_data.to_dict()
            grades.append(grades_item)

        metadata = self.metadata.to_dict()

        session_id = self.session_id

        source = self.source

        created_at = self.created_at.isoformat()

        tool_call_decisions: dict[str, Any] | Unset = UNSET
        if not isinstance(self.tool_call_decisions, Unset):
            tool_call_decisions = self.tool_call_decisions.to_dict()

        gateway_withheld_decisions: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.gateway_withheld_decisions, Unset):
            gateway_withheld_decisions = []
            for gateway_withheld_decisions_item_data in self.gateway_withheld_decisions:
                gateway_withheld_decisions_item = (
                    gateway_withheld_decisions_item_data.to_dict()
                )
                gateway_withheld_decisions.append(gateway_withheld_decisions_item)

        spawned_subagents: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.spawned_subagents, Unset):
            spawned_subagents = []
            for spawned_subagents_item_data in self.spawned_subagents:
                spawned_subagents_item = spawned_subagents_item_data.to_dict()
                spawned_subagents.append(spawned_subagents_item)

        member_trajectory_ids: list[str] | Unset = UNSET
        if not isinstance(self.member_trajectory_ids, Unset):
            member_trajectory_ids = self.member_trajectory_ids

        transcript_revision: None | str | Unset
        if isinstance(self.transcript_revision, Unset):
            transcript_revision = UNSET
        else:
            transcript_revision = self.transcript_revision

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "trajectory_id": trajectory_id,
                "messages": messages,
                "grades": grades,
                "metadata": metadata,
                "session_id": session_id,
                "source": source,
                "created_at": created_at,
            }
        )
        if tool_call_decisions is not UNSET:
            field_dict["tool_call_decisions"] = tool_call_decisions
        if gateway_withheld_decisions is not UNSET:
            field_dict["gateway_withheld_decisions"] = gateway_withheld_decisions
        if spawned_subagents is not UNSET:
            field_dict["spawned_subagents"] = spawned_subagents
        if member_trajectory_ids is not UNSET:
            field_dict["member_trajectory_ids"] = member_trajectory_ids
        if transcript_revision is not UNSET:
            field_dict["transcript_revision"] = transcript_revision

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        from ..models.gateway_withheld_decision_detail import (
            GatewayWithheldDecisionDetail,
        )
        from ..models.grade_result import GradeResult
        from ..models.spawned_subagent import SpawnedSubagent
        from ..models.trajectory_detail_response_messages_item import (
            TrajectoryDetailResponseMessagesItem,
        )
        from ..models.trajectory_detail_response_metadata import (
            TrajectoryDetailResponseMetadata,
        )
        from ..models.trajectory_detail_response_tool_call_decisions import (
            TrajectoryDetailResponseToolCallDecisions,
        )

        d = dict(src_dict)
        trajectory_id = d.pop("trajectory_id")

        messages = []
        _messages = d.pop("messages")
        for messages_item_data in _messages:
            messages_item = TrajectoryDetailResponseMessagesItem.from_dict(
                messages_item_data
            )

            messages.append(messages_item)

        grades = []
        _grades = d.pop("grades")
        for grades_item_data in _grades:
            grades_item = GradeResult.from_dict(grades_item_data)

            grades.append(grades_item)

        metadata = TrajectoryDetailResponseMetadata.from_dict(d.pop("metadata"))

        session_id = d.pop("session_id")

        source = d.pop("source")

        created_at = datetime.datetime.fromisoformat(d.pop("created_at"))

        _tool_call_decisions = d.pop("tool_call_decisions", UNSET)
        tool_call_decisions: TrajectoryDetailResponseToolCallDecisions | Unset
        if isinstance(_tool_call_decisions, Unset):
            tool_call_decisions = UNSET
        else:
            tool_call_decisions = TrajectoryDetailResponseToolCallDecisions.from_dict(
                _tool_call_decisions
            )

        _gateway_withheld_decisions = d.pop("gateway_withheld_decisions", UNSET)
        gateway_withheld_decisions: list[GatewayWithheldDecisionDetail] | Unset = UNSET
        if _gateway_withheld_decisions is not UNSET:
            gateway_withheld_decisions = []
            for gateway_withheld_decisions_item_data in _gateway_withheld_decisions:
                gateway_withheld_decisions_item = (
                    GatewayWithheldDecisionDetail.from_dict(
                        gateway_withheld_decisions_item_data
                    )
                )

                gateway_withheld_decisions.append(gateway_withheld_decisions_item)

        _spawned_subagents = d.pop("spawned_subagents", UNSET)
        spawned_subagents: list[SpawnedSubagent] | Unset = UNSET
        if _spawned_subagents is not UNSET:
            spawned_subagents = []
            for spawned_subagents_item_data in _spawned_subagents:
                spawned_subagents_item = SpawnedSubagent.from_dict(
                    spawned_subagents_item_data
                )

                spawned_subagents.append(spawned_subagents_item)

        member_trajectory_ids = cast(list[str], d.pop("member_trajectory_ids", UNSET))

        def _parse_transcript_revision(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        transcript_revision = _parse_transcript_revision(
            d.pop("transcript_revision", UNSET)
        )

        trajectory_detail_response = cls(
            trajectory_id=trajectory_id,
            messages=messages,
            grades=grades,
            metadata=metadata,
            session_id=session_id,
            source=source,
            created_at=created_at,
            tool_call_decisions=tool_call_decisions,
            gateway_withheld_decisions=gateway_withheld_decisions,
            spawned_subagents=spawned_subagents,
            member_trajectory_ids=member_trajectory_ids,
            transcript_revision=transcript_revision,
        )

        trajectory_detail_response.additional_properties = d
        return trajectory_detail_response

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
