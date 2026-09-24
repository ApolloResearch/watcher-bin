from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.aperture_log import ApertureLog
    from ..models.claude_code_trajectory import ClaudeCodeTrajectory
    from ..models.codex_trajectory import CodexTrajectory


T = TypeVar("T", bound="IngestRequest")


@_attrs_define
class IngestRequest:
    """Request body for POST /v1/ingest.

    Attributes:
        source (str):
        trajectories (list[ApertureLog | ClaudeCodeTrajectory | CodexTrajectory]):
    """

    source: str
    trajectories: list[ApertureLog | ClaudeCodeTrajectory | CodexTrajectory]
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.claude_code_trajectory import ClaudeCodeTrajectory
        from ..models.codex_trajectory import CodexTrajectory

        source = self.source

        trajectories = []
        for trajectories_item_data in self.trajectories:
            trajectories_item: dict[str, Any]
            if isinstance(trajectories_item_data, ClaudeCodeTrajectory):
                trajectories_item = trajectories_item_data.to_dict()
            elif isinstance(trajectories_item_data, CodexTrajectory):
                trajectories_item = trajectories_item_data.to_dict()
            else:
                trajectories_item = trajectories_item_data.to_dict()

            trajectories.append(trajectories_item)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "source": source,
                "trajectories": trajectories,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.aperture_log import ApertureLog
        from ..models.claude_code_trajectory import ClaudeCodeTrajectory
        from ..models.codex_trajectory import CodexTrajectory

        d = dict(src_dict)
        source = d.pop("source")

        trajectories = []
        _trajectories = d.pop("trajectories")
        for trajectories_item_data in _trajectories:

            def _parse_trajectories_item(
                data: object,
            ) -> ApertureLog | ClaudeCodeTrajectory | CodexTrajectory:
                try:
                    if not isinstance(data, dict):
                        raise TypeError()
                    trajectories_item_type_0 = ClaudeCodeTrajectory.from_dict(data)

                    return trajectories_item_type_0
                except (TypeError, ValueError, AttributeError, KeyError):
                    pass
                try:
                    if not isinstance(data, dict):
                        raise TypeError()
                    trajectories_item_type_1 = CodexTrajectory.from_dict(data)

                    return trajectories_item_type_1
                except (TypeError, ValueError, AttributeError, KeyError):
                    pass
                if not isinstance(data, dict):
                    raise TypeError()
                trajectories_item_type_2 = ApertureLog.from_dict(data)

                return trajectories_item_type_2

            trajectories_item = _parse_trajectories_item(trajectories_item_data)

            trajectories.append(trajectories_item)

        ingest_request = cls(
            source=source,
            trajectories=trajectories,
        )

        ingest_request.additional_properties = d
        return ingest_request

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
