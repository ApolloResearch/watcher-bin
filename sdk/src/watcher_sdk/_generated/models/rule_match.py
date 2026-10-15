from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from typing_extensions import Self

T = TypeVar("T", bound="RuleMatch")


@_attrs_define
class RuleMatch:
    """Provenance of a command-rule decision: which rule fired and how.

    Attributes:
        label (str):
        pattern (str):
        action (str):
    """

    label: str
    pattern: str
    action: str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        label = self.label

        pattern = self.pattern

        action = self.action

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "label": label,
                "pattern": pattern,
                "action": action,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        d = dict(src_dict)
        label = d.pop("label")

        pattern = d.pop("pattern")

        action = d.pop("action")

        rule_match = cls(
            label=label,
            pattern=pattern,
            action=action,
        )

        rule_match.additional_properties = d
        return rule_match

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
