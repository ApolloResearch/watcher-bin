from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from typing_extensions import Self

T = TypeVar("T", bound="OrgManagedSettingsResolved")


@_attrs_define
class OrgManagedSettingsResolved:
    """Response for GET /v1/organization/managed-settings/{path}/resolved.

    The machine-pull view: the Watcher Live document a machine should apply.

        Attributes:
            path (str):
            yaml (str):
            version (int):
    """

    path: str
    yaml: str
    version: int
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        path = self.path

        yaml = self.yaml

        version = self.version

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "path": path,
                "yaml": yaml,
                "version": version,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        d = dict(src_dict)
        path = d.pop("path")

        yaml = d.pop("yaml")

        version = d.pop("version")

        org_managed_settings_resolved = cls(
            path=path,
            yaml=yaml,
            version=version,
        )

        org_managed_settings_resolved.additional_properties = d
        return org_managed_settings_resolved

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
