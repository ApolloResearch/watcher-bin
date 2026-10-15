from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from typing_extensions import Self

T = TypeVar(
    "T",
    bound="GetOrgManagedSettingsSchemaV1OrganizationManagedSettingsPathSchemaGetResponseGetOrgManagedSettingsSchemaV1OrganizationManagedSettingsPathSchemaGet",
)


@_attrs_define
class GetOrgManagedSettingsSchemaV1OrganizationManagedSettingsPathSchemaGetResponseGetOrgManagedSettingsSchemaV1OrganizationManagedSettingsPathSchemaGet:
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        d = dict(src_dict)
        get_org_managed_settings_schema_v1_organization_managed_settings_path_schema_get_response_get_org_managed_settings_schema_v1_organization_managed_settings_path_schema_get = cls()

        get_org_managed_settings_schema_v1_organization_managed_settings_path_schema_get_response_get_org_managed_settings_schema_v1_organization_managed_settings_path_schema_get.additional_properties = d
        return get_org_managed_settings_schema_v1_organization_managed_settings_path_schema_get_response_get_org_managed_settings_schema_v1_organization_managed_settings_path_schema_get

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
