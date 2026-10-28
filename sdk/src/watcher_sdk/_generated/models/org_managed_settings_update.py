from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Self, TypeVar

from attrs import define as _attrs_define

T = TypeVar("T", bound="OrgManagedSettingsUpdate")


@_attrs_define
class OrgManagedSettingsUpdate:
    """Request body to save a new version of the org's managed Watcher Live settings document.

    Body for PUT /v1/organization/managed-settings/{path}.

        Attributes:
            yaml (str):
            expected_version (int): Version returned by GET; use 0 when no document exists.
    """

    yaml: str
    expected_version: int

    def to_dict(self) -> dict[str, Any]:
        yaml = self.yaml

        expected_version = self.expected_version

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "yaml": yaml,
                "expected_version": expected_version,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        d = dict(src_dict)
        yaml = d.pop("yaml")

        expected_version = d.pop("expected_version")

        org_managed_settings_update = cls(
            yaml=yaml,
            expected_version=expected_version,
        )

        return org_managed_settings_update
