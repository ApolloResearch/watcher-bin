from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Self, TypeVar, cast
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.agent_inventory_installation_agent import (
        AgentInventoryInstallationAgent,
    )


T = TypeVar("T", bound="AgentInventoryInstallation")


@_attrs_define
class AgentInventoryInstallation:
    """One machine running the Watcher client, with its owner and agents.

    Attributes:
        installation_id (UUID):
        user_id (None | UUID):
        user_name (None | str):
        user_email (None | str): Hidden unless you may read other people's email addresses.
        hostname (None | str):
        os (None | str):
        arch (None | str):
        client_version (None | str):
        first_report_at (datetime.datetime):
        last_report_at (datetime.datetime):
        agents (list[AgentInventoryInstallationAgent]):
    """

    installation_id: UUID
    user_id: None | UUID
    user_name: None | str
    user_email: None | str
    hostname: None | str
    os: None | str
    arch: None | str
    client_version: None | str
    first_report_at: datetime.datetime
    last_report_at: datetime.datetime
    agents: list[AgentInventoryInstallationAgent]
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        installation_id = str(self.installation_id)

        user_id: None | str
        if isinstance(self.user_id, UUID):
            user_id = str(self.user_id)
        else:
            user_id = self.user_id

        user_name: None | str
        user_name = self.user_name

        user_email: None | str
        user_email = self.user_email

        hostname: None | str
        hostname = self.hostname

        os: None | str
        os = self.os

        arch: None | str
        arch = self.arch

        client_version: None | str
        client_version = self.client_version

        first_report_at = self.first_report_at.isoformat()

        last_report_at = self.last_report_at.isoformat()

        agents = []
        for agents_item_data in self.agents:
            agents_item = agents_item_data.to_dict()
            agents.append(agents_item)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "installation_id": installation_id,
                "user_id": user_id,
                "user_name": user_name,
                "user_email": user_email,
                "hostname": hostname,
                "os": os,
                "arch": arch,
                "client_version": client_version,
                "first_report_at": first_report_at,
                "last_report_at": last_report_at,
                "agents": agents,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        from ..models.agent_inventory_installation_agent import (
            AgentInventoryInstallationAgent,
        )

        d = dict(src_dict)
        installation_id = UUID(d.pop("installation_id"))

        def _parse_user_id(data: object) -> None | UUID:
            if data is None:
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                user_id_type_0 = UUID(data)

                return user_id_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | UUID, data)

        user_id = _parse_user_id(d.pop("user_id"))

        def _parse_user_name(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        user_name = _parse_user_name(d.pop("user_name"))

        def _parse_user_email(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        user_email = _parse_user_email(d.pop("user_email"))

        def _parse_hostname(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        hostname = _parse_hostname(d.pop("hostname"))

        def _parse_os(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        os = _parse_os(d.pop("os"))

        def _parse_arch(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        arch = _parse_arch(d.pop("arch"))

        def _parse_client_version(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        client_version = _parse_client_version(d.pop("client_version"))

        first_report_at = datetime.datetime.fromisoformat(d.pop("first_report_at"))

        last_report_at = datetime.datetime.fromisoformat(d.pop("last_report_at"))

        agents = []
        _agents = d.pop("agents")
        for agents_item_data in _agents:
            agents_item = AgentInventoryInstallationAgent.from_dict(agents_item_data)

            agents.append(agents_item)

        agent_inventory_installation = cls(
            installation_id=installation_id,
            user_id=user_id,
            user_name=user_name,
            user_email=user_email,
            hostname=hostname,
            os=os,
            arch=arch,
            client_version=client_version,
            first_report_at=first_report_at,
            last_report_at=last_report_at,
            agents=agents,
        )

        agent_inventory_installation.additional_properties = d
        return agent_inventory_installation

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
