from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Self, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.trajectory_summary import TrajectorySummary


T = TypeVar("T", bound="TrajectoryListInSessionResponse")


@_attrs_define
class TrajectoryListInSessionResponse:
    """Response from GET /v1/sessions/{session_id}/trajectories.

    Attributes:
        trajectories (list[TrajectorySummary]):
        total (int):
    """

    trajectories: list[TrajectorySummary]
    total: int
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        trajectories = []
        for trajectories_item_data in self.trajectories:
            trajectories_item = trajectories_item_data.to_dict()
            trajectories.append(trajectories_item)

        total = self.total

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "trajectories": trajectories,
                "total": total,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        from ..models.trajectory_summary import TrajectorySummary

        d = dict(src_dict)
        trajectories = []
        _trajectories = d.pop("trajectories")
        for trajectories_item_data in _trajectories:
            trajectories_item = TrajectorySummary.from_dict(trajectories_item_data)

            trajectories.append(trajectories_item)

        total = d.pop("total")

        trajectory_list_in_session_response = cls(
            trajectories=trajectories,
            total=total,
        )

        trajectory_list_in_session_response.additional_properties = d
        return trajectory_list_in_session_response

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
