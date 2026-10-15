from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from typing_extensions import Self

T = TypeVar("T", bound="GradingUsageUserOption")


@_attrs_define
class GradingUsageUserOption:
    """A user available as a grading-usage filter value.

    Attributes:
        user_id (UUID):
        email (str):
    """

    user_id: UUID
    email: str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        user_id = str(self.user_id)

        email = self.email

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "user_id": user_id,
                "email": email,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        d = dict(src_dict)
        user_id = UUID(d.pop("user_id"))

        email = d.pop("email")

        grading_usage_user_option = cls(
            user_id=user_id,
            email=email,
        )

        grading_usage_user_option.additional_properties = d
        return grading_usage_user_option

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
