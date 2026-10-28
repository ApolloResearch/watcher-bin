from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Self, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.suggested_model import SuggestedModel


T = TypeVar("T", bound="ModelsConfig")


@_attrs_define
class ModelsConfig:
    """Response shape of ``GET /v1/graders/models``, built from the model catalog.

    ``suggested`` are catalog entries advertised in the UI; ``enabled`` are the
    remaining allowed models (accepted by the free-text input, not advertised
    in dropdowns).

        Attributes:
            suggested (list[SuggestedModel]):
            enabled (list[str]):
    """

    suggested: list[SuggestedModel]
    enabled: list[str]
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        suggested = []
        for suggested_item_data in self.suggested:
            suggested_item = suggested_item_data.to_dict()
            suggested.append(suggested_item)

        enabled = self.enabled

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "suggested": suggested,
                "enabled": enabled,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        from ..models.suggested_model import SuggestedModel

        d = dict(src_dict)
        suggested = []
        _suggested = d.pop("suggested")
        for suggested_item_data in _suggested:
            suggested_item = SuggestedModel.from_dict(suggested_item_data)

            suggested.append(suggested_item)

        enabled = cast(list[str], d.pop("enabled"))

        models_config = cls(
            suggested=suggested,
            enabled=enabled,
        )

        models_config.additional_properties = d
        return models_config

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
