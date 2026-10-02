from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.deep_review_request_response import DeepReviewRequestResponse


T = TypeVar("T", bound="SessionDeepReviewResponse")


@_attrs_define
class SessionDeepReviewResponse:
    """The deep-review work a session viewer should see on load.

    ``current`` is an unfinished review if one exists, whoever queued it;
    otherwise the latest review of the session's current transcript; otherwise
    null, meaning no review was ever requested for it.

        Attributes:
            current (DeepReviewRequestResponse | None):
    """

    current: DeepReviewRequestResponse | None
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.deep_review_request_response import DeepReviewRequestResponse

        current: dict[str, Any] | None
        if isinstance(self.current, DeepReviewRequestResponse):
            current = self.current.to_dict()
        else:
            current = self.current

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "current": current,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.deep_review_request_response import DeepReviewRequestResponse

        d = dict(src_dict)

        def _parse_current(data: object) -> DeepReviewRequestResponse | None:
            if data is None:
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                current_type_0 = DeepReviewRequestResponse.from_dict(data)

                return current_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(DeepReviewRequestResponse | None, data)

        current = _parse_current(d.pop("current"))

        session_deep_review_response = cls(
            current=current,
        )

        session_deep_review_response.additional_properties = d
        return session_deep_review_response

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
