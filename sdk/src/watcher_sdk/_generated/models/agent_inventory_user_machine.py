from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import Any, Self, TypeVar, cast
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="AgentInventoryUserMachine")


@_attrs_define
class AgentInventoryUserMachine:
    """One of a person's machines running the Watcher client.

    Attributes:
        installation_id (UUID):
        hostname (None | str):
        os (None | str):
        last_report_at (datetime.datetime):
    """

    installation_id: UUID
    hostname: None | str
    os: None | str
    last_report_at: datetime.datetime
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        installation_id = str(self.installation_id)

        hostname: None | str
        hostname = self.hostname

        os: None | str
        os = self.os

        last_report_at = self.last_report_at.isoformat()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "installation_id": installation_id,
                "hostname": hostname,
                "os": os,
                "last_report_at": last_report_at,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        d = dict(src_dict)
        installation_id = UUID(d.pop("installation_id"))

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

        last_report_at = datetime.datetime.fromisoformat(d.pop("last_report_at"))

        agent_inventory_user_machine = cls(
            installation_id=installation_id,
            hostname=hostname,
            os=os,
            last_report_at=last_report_at,
        )

        agent_inventory_user_machine.additional_properties = d
        return agent_inventory_user_machine

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
