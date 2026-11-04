from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Self, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.agent_inventory_report_agent import AgentInventoryReportAgent


T = TypeVar("T", bound="AgentInventoryStatus")


@_attrs_define
class AgentInventoryStatus:
    """The `inventory` section of an installation report: the coding agents one scan found on the machine.

    Send the full list each time.

        Attributes:
            observed_at (datetime.datetime): When the Watcher client ran the scan. A retried report keeps its original time.
            client_version (None | str | Unset):
            hostname (None | str | Unset):
            os (None | str | Unset): `macos` or `linux`.
            arch (None | str | Unset): `arm64` or `x86_64`.
            agents (list[AgentInventoryReportAgent] | Unset):
    """

    observed_at: datetime.datetime
    client_version: None | str | Unset = UNSET
    hostname: None | str | Unset = UNSET
    os: None | str | Unset = UNSET
    arch: None | str | Unset = UNSET
    agents: list[AgentInventoryReportAgent] | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        observed_at = self.observed_at.isoformat()

        client_version: None | str | Unset
        if isinstance(self.client_version, Unset):
            client_version = UNSET
        else:
            client_version = self.client_version

        hostname: None | str | Unset
        if isinstance(self.hostname, Unset):
            hostname = UNSET
        else:
            hostname = self.hostname

        os: None | str | Unset
        if isinstance(self.os, Unset):
            os = UNSET
        else:
            os = self.os

        arch: None | str | Unset
        if isinstance(self.arch, Unset):
            arch = UNSET
        else:
            arch = self.arch

        agents: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.agents, Unset):
            agents = []
            for agents_item_data in self.agents:
                agents_item = agents_item_data.to_dict()
                agents.append(agents_item)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "observed_at": observed_at,
            }
        )
        if client_version is not UNSET:
            field_dict["client_version"] = client_version
        if hostname is not UNSET:
            field_dict["hostname"] = hostname
        if os is not UNSET:
            field_dict["os"] = os
        if arch is not UNSET:
            field_dict["arch"] = arch
        if agents is not UNSET:
            field_dict["agents"] = agents

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        from ..models.agent_inventory_report_agent import AgentInventoryReportAgent

        d = dict(src_dict)
        observed_at = datetime.datetime.fromisoformat(d.pop("observed_at"))

        def _parse_client_version(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        client_version = _parse_client_version(d.pop("client_version", UNSET))

        def _parse_hostname(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        hostname = _parse_hostname(d.pop("hostname", UNSET))

        def _parse_os(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        os = _parse_os(d.pop("os", UNSET))

        def _parse_arch(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        arch = _parse_arch(d.pop("arch", UNSET))

        _agents = d.pop("agents", UNSET)
        agents: list[AgentInventoryReportAgent] | Unset = UNSET
        if _agents is not UNSET:
            agents = []
            for agents_item_data in _agents:
                agents_item = AgentInventoryReportAgent.from_dict(agents_item_data)

                agents.append(agents_item)

        agent_inventory_status = cls(
            observed_at=observed_at,
            client_version=client_version,
            hostname=hostname,
            os=os,
            arch=arch,
            agents=agents,
        )

        agent_inventory_status.additional_properties = d
        return agent_inventory_status

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
