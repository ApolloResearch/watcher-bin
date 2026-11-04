from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Self, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="SessionFilterOptionsResponse")


@_attrs_define
class SessionFilterOptionsResponse:
    """Available filter options for session list/search responses.

    Attributes:
        grader_score_categories (list[str]):
        hostnames (list[str] | Unset): Machine hostnames recorded on sessions the caller can read, sorted, at most 500.
            Values for the `hostnames` search filter.
    """

    grader_score_categories: list[str]
    hostnames: list[str] | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        grader_score_categories = self.grader_score_categories

        hostnames: list[str] | Unset = UNSET
        if not isinstance(self.hostnames, Unset):
            hostnames = self.hostnames

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "grader_score_categories": grader_score_categories,
            }
        )
        if hostnames is not UNSET:
            field_dict["hostnames"] = hostnames

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        d = dict(src_dict)
        grader_score_categories = cast(list[str], d.pop("grader_score_categories"))

        hostnames = cast(list[str], d.pop("hostnames", UNSET))

        session_filter_options_response = cls(
            grader_score_categories=grader_score_categories,
            hostnames=hostnames,
        )

        session_filter_options_response.additional_properties = d
        return session_filter_options_response

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
