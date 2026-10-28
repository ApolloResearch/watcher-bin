from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Self, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.grading_usage_grader_option import GradingUsageGraderOption
    from ..models.grading_usage_user_option import GradingUsageUserOption


T = TypeVar("T", bound="GradingUsageFilterOptions")


@_attrs_define
class GradingUsageFilterOptions:
    """Distinct filterable values for the grading-usage view.

    ``users`` and ``graders`` are org-wide; ``models`` only includes models
    with usage inside the requested date window, so the picker never offers a
    model that would chart nothing.

        Attributes:
            users (list[GradingUsageUserOption]):
            models (list[str]):
            graders (list[GradingUsageGraderOption]):
    """

    users: list[GradingUsageUserOption]
    models: list[str]
    graders: list[GradingUsageGraderOption]
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        users = []
        for users_item_data in self.users:
            users_item = users_item_data.to_dict()
            users.append(users_item)

        models = self.models

        graders = []
        for graders_item_data in self.graders:
            graders_item = graders_item_data.to_dict()
            graders.append(graders_item)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "users": users,
                "models": models,
                "graders": graders,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        from ..models.grading_usage_grader_option import GradingUsageGraderOption
        from ..models.grading_usage_user_option import GradingUsageUserOption

        d = dict(src_dict)
        users = []
        _users = d.pop("users")
        for users_item_data in _users:
            users_item = GradingUsageUserOption.from_dict(users_item_data)

            users.append(users_item)

        models = cast(list[str], d.pop("models"))

        graders = []
        _graders = d.pop("graders")
        for graders_item_data in _graders:
            graders_item = GradingUsageGraderOption.from_dict(graders_item_data)

            graders.append(graders_item)

        grading_usage_filter_options = cls(
            users=users,
            models=models,
            graders=graders,
        )

        grading_usage_filter_options.additional_properties = d
        return grading_usage_filter_options

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
