from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Self, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.installation_report_error_detail import InstallationReportErrorDetail


T = TypeVar("T", bound="InstallationReportErrorResponse")


@_attrs_define
class InstallationReportErrorResponse:
    """An installation report error.

    Attributes:
        detail (InstallationReportErrorDetail): A machine-readable error code and a human-readable message.
    """

    detail: InstallationReportErrorDetail
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        detail = self.detail.to_dict()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "detail": detail,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        from ..models.installation_report_error_detail import (
            InstallationReportErrorDetail,
        )

        d = dict(src_dict)
        detail = InstallationReportErrorDetail.from_dict(d.pop("detail"))

        installation_report_error_response = cls(
            detail=detail,
        )

        installation_report_error_response.additional_properties = d
        return installation_report_error_response

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
