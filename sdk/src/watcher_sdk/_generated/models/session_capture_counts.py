from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Self, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="SessionCaptureCounts")


@_attrs_define
class SessionCaptureCounts:
    """Visible sessions counted independently for each recorded ingestion path.

    A session can contribute to several source counts. Each count uses the
    containing summary's total_sessions as its denominator, so shares can sum
    above 100%. Source presence covers the whole session and survives content
    scrubbing; unknown means no recoverable source record. These counts
    describe recorded uploads, not installation, grading or complete coverage.

        Attributes:
            client (int):
            gateway (int):
            sdk (int):
            other (int):
            unknown (int):
    """

    client: int
    gateway: int
    sdk: int
    other: int
    unknown: int
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        client = self.client

        gateway = self.gateway

        sdk = self.sdk

        other = self.other

        unknown = self.unknown

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "client": client,
                "gateway": gateway,
                "sdk": sdk,
                "other": other,
                "unknown": unknown,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        d = dict(src_dict)
        client = d.pop("client")

        gateway = d.pop("gateway")

        sdk = d.pop("sdk")

        other = d.pop("other")

        unknown = d.pop("unknown")

        session_capture_counts = cls(
            client=client,
            gateway=gateway,
            sdk=sdk,
            other=other,
            unknown=unknown,
        )

        session_capture_counts.additional_properties = d
        return session_capture_counts

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
