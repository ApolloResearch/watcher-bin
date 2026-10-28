from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Self, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.score_definition_type import ScoreDefinitionType
from ..types import UNSET, Unset

T = TypeVar("T", bound="ScoreDefinition")


@_attrs_define
class ScoreDefinition:
    """Definition of a single score dimension. Used in both requests and responses.

    The ``name`` is a human-readable label (e.g., "API Key Mishandling").
    The ``description`` is a short summary for display.
    The ``definition`` holds the full rubric text that gets composed into the grading prompt.

    ``name`` and ``definition`` are optional for backward compatibility with graders
    migrated before structured score definitions were introduced.

        Attributes:
            type_ (ScoreDefinitionType):
            description (str):
            name (None | str | Unset):
            definition (None | str | Unset):
            min_value (float | None | Unset):
            max_value (float | None | Unset):
    """

    type_: ScoreDefinitionType
    description: str
    name: None | str | Unset = UNSET
    definition: None | str | Unset = UNSET
    min_value: float | None | Unset = UNSET
    max_value: float | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        type_ = self.type_.value

        description = self.description

        name: None | str | Unset
        if isinstance(self.name, Unset):
            name = UNSET
        else:
            name = self.name

        definition: None | str | Unset
        if isinstance(self.definition, Unset):
            definition = UNSET
        else:
            definition = self.definition

        min_value: float | None | Unset
        if isinstance(self.min_value, Unset):
            min_value = UNSET
        else:
            min_value = self.min_value

        max_value: float | None | Unset
        if isinstance(self.max_value, Unset):
            max_value = UNSET
        else:
            max_value = self.max_value

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "type": type_,
                "description": description,
            }
        )
        if name is not UNSET:
            field_dict["name"] = name
        if definition is not UNSET:
            field_dict["definition"] = definition
        if min_value is not UNSET:
            field_dict["min_value"] = min_value
        if max_value is not UNSET:
            field_dict["max_value"] = max_value

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        d = dict(src_dict)
        type_ = ScoreDefinitionType(d.pop("type"))

        description = d.pop("description")

        def _parse_name(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        name = _parse_name(d.pop("name", UNSET))

        def _parse_definition(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        definition = _parse_definition(d.pop("definition", UNSET))

        def _parse_min_value(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        min_value = _parse_min_value(d.pop("min_value", UNSET))

        def _parse_max_value(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        max_value = _parse_max_value(d.pop("max_value", UNSET))

        score_definition = cls(
            type_=type_,
            description=description,
            name=name,
            definition=definition,
            min_value=min_value,
            max_value=max_value,
        )

        score_definition.additional_properties = d
        return score_definition

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
