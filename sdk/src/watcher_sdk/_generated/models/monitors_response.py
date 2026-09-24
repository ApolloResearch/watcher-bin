from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.monitor_info import MonitorInfo


T = TypeVar("T", bound="MonitorsResponse")


@_attrs_define
class MonitorsResponse:
    """Response for GET /v1/monitors.

    Also the monitoring capability signal: a server without server-managed
    monitors 404s this path, telling a client to stay on grader-UUID grading.

        Attributes:
            monitors (list[MonitorInfo]):
    """

    monitors: list[MonitorInfo]
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        monitors = []
        for monitors_item_data in self.monitors:
            monitors_item = monitors_item_data.to_dict()
            monitors.append(monitors_item)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "monitors": monitors,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.monitor_info import MonitorInfo

        d = dict(src_dict)
        monitors = []
        _monitors = d.pop("monitors")
        for monitors_item_data in _monitors:
            monitors_item = MonitorInfo.from_dict(monitors_item_data)

            monitors.append(monitors_item)

        monitors_response = cls(
            monitors=monitors,
        )

        monitors_response.additional_properties = d
        return monitors_response

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
