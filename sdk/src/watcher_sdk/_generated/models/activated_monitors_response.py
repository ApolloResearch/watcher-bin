from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.activated_monitors_response_distribution import (
    ActivatedMonitorsResponseDistribution,
)
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.activated_monitor import ActivatedMonitor


T = TypeVar("T", bound="ActivatedMonitorsResponse")


@_attrs_define
class ActivatedMonitorsResponse:
    """Response for GET /v1/organization/managed-settings/{path}/monitors.

    A read-only projection of which custom or managed monitors the current
    document activates. Consumed by the Monitors page rollout badges and the
    draft-assist and red-team prompts on the Managed Settings page. Managed
    identities describe current-client routing, not observed fleet activity.

    `monitors` is populated only when the org distributes via Watcher: under MDM
    the stored document is not what runs on machines, so rollout cannot be
    asserted and the list is empty. `distribution` is included so the response is
    self-interpreting (an empty list means "nothing activated" under `watcher`
    but "not applicable" under `mdm`). `version` is the document version the list
    was computed from (0 when none saved).

        Attributes:
            distribution (ActivatedMonitorsResponseDistribution):
            version (int | Unset):  Default: 0.
            monitors (list[ActivatedMonitor] | Unset):
    """

    distribution: ActivatedMonitorsResponseDistribution
    version: int | Unset = 0
    monitors: list[ActivatedMonitor] | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        distribution = self.distribution.value

        version = self.version

        monitors: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.monitors, Unset):
            monitors = []
            for monitors_item_data in self.monitors:
                monitors_item = monitors_item_data.to_dict()
                monitors.append(monitors_item)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "distribution": distribution,
            }
        )
        if version is not UNSET:
            field_dict["version"] = version
        if monitors is not UNSET:
            field_dict["monitors"] = monitors

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.activated_monitor import ActivatedMonitor

        d = dict(src_dict)
        distribution = ActivatedMonitorsResponseDistribution(d.pop("distribution"))

        version = d.pop("version", UNSET)

        _monitors = d.pop("monitors", UNSET)
        monitors: list[ActivatedMonitor] | Unset = UNSET
        if _monitors is not UNSET:
            monitors = []
            for monitors_item_data in _monitors:
                monitors_item = ActivatedMonitor.from_dict(monitors_item_data)

                monitors.append(monitors_item)

        activated_monitors_response = cls(
            distribution=distribution,
            version=version,
            monitors=monitors,
        )

        activated_monitors_response.additional_properties = d
        return activated_monitors_response

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
