from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.claude_code_trajectory import ClaudeCodeTrajectory
    from ..models.codex_trajectory import CodexTrajectory


T = TypeVar("T", bound="IngestAppendRequest")


@_attrs_define
class IngestAppendRequest:
    """Request body for POST /v1/sessions/{session_id}/trajectories/{trajectory_id}/append.

    Appends a delta of raw transcript entries to an existing session's chain.
    The session and the anchor (the trajectory_id of the last message the
    client successfully uploaded) are named in the path; the server continues
    the chain after the anchor, so a session ingested through any mix of full
    and append uploads stores rows identical to full-only ingestion. Tailscale
    Aperture logs are whole-file proxy captures with no client-side cursor, so
    they have no append form.

        Attributes:
            source (str):
            trajectory (ClaudeCodeTrajectory | CodexTrajectory):
    """

    source: str
    trajectory: ClaudeCodeTrajectory | CodexTrajectory
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.claude_code_trajectory import ClaudeCodeTrajectory

        source = self.source

        trajectory: dict[str, Any]
        if isinstance(self.trajectory, ClaudeCodeTrajectory):
            trajectory = self.trajectory.to_dict()
        else:
            trajectory = self.trajectory.to_dict()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "source": source,
                "trajectory": trajectory,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.claude_code_trajectory import ClaudeCodeTrajectory
        from ..models.codex_trajectory import CodexTrajectory

        d = dict(src_dict)
        source = d.pop("source")

        def _parse_trajectory(data: object) -> ClaudeCodeTrajectory | CodexTrajectory:
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                trajectory_type_0 = ClaudeCodeTrajectory.from_dict(data)

                return trajectory_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            if not isinstance(data, dict):
                raise TypeError()
            trajectory_type_1 = CodexTrajectory.from_dict(data)

            return trajectory_type_1

        trajectory = _parse_trajectory(d.pop("trajectory"))

        ingest_append_request = cls(
            source=source,
            trajectory=trajectory,
        )

        ingest_append_request.additional_properties = d
        return ingest_append_request

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
