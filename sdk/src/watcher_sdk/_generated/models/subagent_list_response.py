from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Self, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.related_session_summary import RelatedSessionSummary


T = TypeVar("T", bound="SubagentListResponse")


@_attrs_define
class SubagentListResponse:
    """One page of readable immediate children; the total excludes inaccessible sessions.

    Attributes:
        sessions (list[RelatedSessionSummary]):
        total (int):
        limit (int):
        offset (int):
    """

    sessions: list[RelatedSessionSummary]
    total: int
    limit: int
    offset: int
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        sessions = []
        for sessions_item_data in self.sessions:
            sessions_item = sessions_item_data.to_dict()
            sessions.append(sessions_item)

        total = self.total

        limit = self.limit

        offset = self.offset

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "sessions": sessions,
                "total": total,
                "limit": limit,
                "offset": offset,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        from ..models.related_session_summary import RelatedSessionSummary

        d = dict(src_dict)
        sessions = []
        _sessions = d.pop("sessions")
        for sessions_item_data in _sessions:
            sessions_item = RelatedSessionSummary.from_dict(sessions_item_data)

            sessions.append(sessions_item)

        total = d.pop("total")

        limit = d.pop("limit")

        offset = d.pop("offset")

        subagent_list_response = cls(
            sessions=sessions,
            total=total,
            limit=limit,
            offset=offset,
        )

        subagent_list_response.additional_properties = d
        return subagent_list_response

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
