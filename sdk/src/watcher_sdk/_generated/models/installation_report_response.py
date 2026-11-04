from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Self, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.installation_report_response_result import (
    InstallationReportResponseResult,
)

T = TypeVar("T", bound="InstallationReportResponse")


@_attrs_define
class InstallationReportResponse:
    """What the report did: `stored` for a new report, `duplicate` when this report ID was already stored.

    Attributes:
        result (InstallationReportResponseResult):
    """

    result: InstallationReportResponseResult
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        result = self.result.value

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "result": result,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        d = dict(src_dict)
        result = InstallationReportResponseResult(d.pop("result"))

        installation_report_response = cls(
            result=result,
        )

        installation_report_response.additional_properties = d
        return installation_report_response

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
