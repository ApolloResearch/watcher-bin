from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from typing_extensions import Self

from ..models.managed_settings_source_error_kind_type_0 import (
    ManagedSettingsSourceErrorKindType0,
)
from ..types import UNSET, Unset

T = TypeVar("T", bound="ManagedSettingsSource")


@_attrs_define
class ManagedSettingsSource:
    """Where the organization's managed settings document is coming from when an admin cannot edit it.

    Present on `OrgSettings` only when the deployment mounts a managed settings
    file (self-host). `path` is the file inside the API container and
    `modified_at` the file's modification time when the content now in force
    was read, so every API worker reports the same value. When the latest
    state of the file could not be applied, `error_kind` says why and `error`
    gives a short human-readable reason (validation messages name setting
    paths, never document content); the previous content stays in force.

        Attributes:
            path (str):
            modified_at (datetime.datetime):
            error_kind (ManagedSettingsSourceErrorKindType0 | None | Unset):
            error (None | str | Unset):
    """

    path: str
    modified_at: datetime.datetime
    error_kind: ManagedSettingsSourceErrorKindType0 | None | Unset = UNSET
    error: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        path = self.path

        modified_at = self.modified_at.isoformat()

        error_kind: None | str | Unset
        if isinstance(self.error_kind, Unset):
            error_kind = UNSET
        elif isinstance(self.error_kind, ManagedSettingsSourceErrorKindType0):
            error_kind = self.error_kind.value
        else:
            error_kind = self.error_kind

        error: None | str | Unset
        if isinstance(self.error, Unset):
            error = UNSET
        else:
            error = self.error

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "path": path,
                "modified_at": modified_at,
            }
        )
        if error_kind is not UNSET:
            field_dict["error_kind"] = error_kind
        if error is not UNSET:
            field_dict["error"] = error

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        d = dict(src_dict)
        path = d.pop("path")

        modified_at = datetime.datetime.fromisoformat(d.pop("modified_at"))

        def _parse_error_kind(
            data: object,
        ) -> ManagedSettingsSourceErrorKindType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                error_kind_type_0 = ManagedSettingsSourceErrorKindType0(data)

                return error_kind_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(ManagedSettingsSourceErrorKindType0 | None | Unset, data)

        error_kind = _parse_error_kind(d.pop("error_kind", UNSET))

        def _parse_error(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        error = _parse_error(d.pop("error", UNSET))

        managed_settings_source = cls(
            path=path,
            modified_at=modified_at,
            error_kind=error_kind,
            error=error,
        )

        managed_settings_source.additional_properties = d
        return managed_settings_source

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
