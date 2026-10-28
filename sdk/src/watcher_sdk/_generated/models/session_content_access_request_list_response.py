from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Self, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.session_content_access_request_summary import (
        SessionContentAccessRequestSummary,
    )


T = TypeVar("T", bound="SessionContentAccessRequestListResponse")


@_attrs_define
class SessionContentAccessRequestListResponse:
    """A page of the caller's requests, ordered newest first.

    Attributes:
        requests (list[SessionContentAccessRequestSummary]):
        total (int):
        limit (int):
        offset (int):
    """

    requests: list[SessionContentAccessRequestSummary]
    total: int
    limit: int
    offset: int
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        requests = []
        for requests_item_data in self.requests:
            requests_item = requests_item_data.to_dict()
            requests.append(requests_item)

        total = self.total

        limit = self.limit

        offset = self.offset

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "requests": requests,
                "total": total,
                "limit": limit,
                "offset": offset,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        from ..models.session_content_access_request_summary import (
            SessionContentAccessRequestSummary,
        )

        d = dict(src_dict)
        requests = []
        _requests = d.pop("requests")
        for requests_item_data in _requests:
            requests_item = SessionContentAccessRequestSummary.from_dict(
                requests_item_data
            )

            requests.append(requests_item)

        total = d.pop("total")

        limit = d.pop("limit")

        offset = d.pop("offset")

        session_content_access_request_list_response = cls(
            requests=requests,
            total=total,
            limit=limit,
            offset=offset,
        )

        session_content_access_request_list_response.additional_properties = d
        return session_content_access_request_list_response

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
