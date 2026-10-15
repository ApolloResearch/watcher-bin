from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from typing_extensions import Self

from ..models.deep_review_request_response_status import DeepReviewRequestResponseStatus

T = TypeVar("T", bound="DeepReviewRequestResponse")


@_attrs_define
class DeepReviewRequestResponse:
    """Queue state of an on-demand deep review, for polling until it finishes.

    ``queued`` and ``running`` are in progress. ``succeeded`` means the review
    finished; its report is published as the session's deep-review grade unless
    a newer review already replaced it. ``failed`` means the review gave up after
    its retries or was cancelled; send the request again to start a new review
    (refused with 409 once this transcript has failed too many times).

        Attributes:
            operation_id (UUID):
            status (DeepReviewRequestResponseStatus):
            trajectory_hash (str):
            can_retry (bool):
    """

    operation_id: UUID
    status: DeepReviewRequestResponseStatus
    trajectory_hash: str
    can_retry: bool
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        operation_id = str(self.operation_id)

        status = self.status.value

        trajectory_hash = self.trajectory_hash

        can_retry = self.can_retry

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "operation_id": operation_id,
                "status": status,
                "trajectory_hash": trajectory_hash,
                "can_retry": can_retry,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        d = dict(src_dict)
        operation_id = UUID(d.pop("operation_id"))

        status = DeepReviewRequestResponseStatus(d.pop("status"))

        trajectory_hash = d.pop("trajectory_hash")

        can_retry = d.pop("can_retry")

        deep_review_request_response = cls(
            operation_id=operation_id,
            status=status,
            trajectory_hash=trajectory_hash,
            can_retry=can_retry,
        )

        deep_review_request_response.additional_properties = d
        return deep_review_request_response

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
