from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from dateutil.parser import isoparse

from ..types import UNSET, Unset

T = TypeVar("T", bound="OrgManagedSettingsDoc")


@_attrs_define
class OrgManagedSettingsDoc:
    """Response for GET/PUT /v1/organization/managed-settings/{path}.

    The document is the organization's managed Watcher Live configuration: the
    ``settings.yaml`` that machines running Watcher Live apply. `yaml` is null
    (and `version` 0) when the org has never saved a document for this path. This
    response carries only the document; the org-level distribution policy lives
    on OrgSettings.

        Attributes:
            path (str):
            yaml (None | str | Unset):
            version (int | Unset):  Default: 0.
            updated_at (datetime.datetime | None | Unset):
            updated_by (None | str | Unset):
    """

    path: str
    yaml: None | str | Unset = UNSET
    version: int | Unset = 0
    updated_at: datetime.datetime | None | Unset = UNSET
    updated_by: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        path = self.path

        yaml: None | str | Unset
        if isinstance(self.yaml, Unset):
            yaml = UNSET
        else:
            yaml = self.yaml

        version = self.version

        updated_at: None | str | Unset
        if isinstance(self.updated_at, Unset):
            updated_at = UNSET
        elif isinstance(self.updated_at, datetime.datetime):
            updated_at = self.updated_at.isoformat()
        else:
            updated_at = self.updated_at

        updated_by: None | str | Unset
        if isinstance(self.updated_by, Unset):
            updated_by = UNSET
        else:
            updated_by = self.updated_by

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "path": path,
            }
        )
        if yaml is not UNSET:
            field_dict["yaml"] = yaml
        if version is not UNSET:
            field_dict["version"] = version
        if updated_at is not UNSET:
            field_dict["updated_at"] = updated_at
        if updated_by is not UNSET:
            field_dict["updated_by"] = updated_by

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        path = d.pop("path")

        def _parse_yaml(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        yaml = _parse_yaml(d.pop("yaml", UNSET))

        version = d.pop("version", UNSET)

        def _parse_updated_at(data: object) -> datetime.datetime | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                updated_at_type_0 = isoparse(data)

                return updated_at_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None | Unset, data)

        updated_at = _parse_updated_at(d.pop("updated_at", UNSET))

        def _parse_updated_by(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        updated_by = _parse_updated_by(d.pop("updated_by", UNSET))

        org_managed_settings_doc = cls(
            path=path,
            yaml=yaml,
            version=version,
            updated_at=updated_at,
            updated_by=updated_by,
        )

        org_managed_settings_doc.additional_properties = d
        return org_managed_settings_doc

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
