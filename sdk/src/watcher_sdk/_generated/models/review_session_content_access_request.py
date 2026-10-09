from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from dateutil.parser import isoparse

from ..models.review_session_content_access_request_status import (
    ReviewSessionContentAccessRequestStatus,
)
from ..types import UNSET, Unset

T = TypeVar("T", bound="ReviewSessionContentAccessRequest")


@_attrs_define
class ReviewSessionContentAccessRequest:
    """A final decision; approvals default to eight hours and may use a shorter expiry.

    Attributes:
        status (ReviewSessionContentAccessRequestStatus):
        valid_until (datetime.datetime | None | Unset):
    """

    status: ReviewSessionContentAccessRequestStatus
    valid_until: datetime.datetime | None | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        status = self.status.value

        valid_until: None | str | Unset
        if isinstance(self.valid_until, Unset):
            valid_until = UNSET
        elif isinstance(self.valid_until, datetime.datetime):
            valid_until = self.valid_until.isoformat()
        else:
            valid_until = self.valid_until

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "status": status,
            }
        )
        if valid_until is not UNSET:
            field_dict["valid_until"] = valid_until

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        status = ReviewSessionContentAccessRequestStatus(d.pop("status"))

        def _parse_valid_until(data: object) -> datetime.datetime | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                valid_until_type_0 = isoparse(data)

                return valid_until_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None | Unset, data)

        valid_until = _parse_valid_until(d.pop("valid_until", UNSET))

        review_session_content_access_request = cls(
            status=status,
            valid_until=valid_until,
        )

        return review_session_content_access_request
