from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Self, TypeVar
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.installation_status import InstallationStatus


T = TypeVar("T", bound="InstallationReport")


@_attrs_define
class InstallationReport:
    """One report from a Watcher client installation.

    Attributes:
        report_id (UUID): A random ID for this report. Retry a failed request with the same ID; it is stored once.
        status (InstallationStatus): What the installation is reporting, by section. Omit a section to report nothing
            about it.
    """

    report_id: UUID
    status: InstallationStatus
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        report_id = str(self.report_id)

        status = self.status.to_dict()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "report_id": report_id,
                "status": status,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        from ..models.installation_status import InstallationStatus

        d = dict(src_dict)
        report_id = UUID(d.pop("report_id"))

        status = InstallationStatus.from_dict(d.pop("status"))

        installation_report = cls(
            report_id=report_id,
            status=status,
        )

        installation_report.additional_properties = d
        return installation_report

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
