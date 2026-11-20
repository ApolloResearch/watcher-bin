from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Self, TypeVar, cast
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.agent_inventory_presence import AgentInventoryPresence


T = TypeVar("T", bound="AgentInventoryUserMachine")


@_attrs_define
class AgentInventoryUserMachine:
    """One of a person's machines running the Watcher client, with whether it is online.

    For its endpoint health, read the machine list (`GET /v1/agent-inventory/installations`), whose entry carries
    the same online status.

        Attributes:
            installation_id (UUID):
            hostname (None | str): From the newest inventory scan; null when none was collected.
            os (None | str): From the newest inventory scan; null when none was collected.
            last_report_at (datetime.datetime): When the newest report of any kind from this machine arrived.
            presence (AgentInventoryPresence | None): Whether the machine's Watcher client is online; null while agent
                inventory is off and the client sends no heartbeat, because no new report from it is stored and whether it is
                online cannot be judged.
    """

    installation_id: UUID
    hostname: None | str
    os: None | str
    last_report_at: datetime.datetime
    presence: AgentInventoryPresence | None
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.agent_inventory_presence import AgentInventoryPresence

        installation_id = str(self.installation_id)

        hostname: None | str
        hostname = self.hostname

        os: None | str
        os = self.os

        last_report_at = self.last_report_at.isoformat()

        presence: dict[str, Any] | None
        if isinstance(self.presence, AgentInventoryPresence):
            presence = self.presence.to_dict()
        else:
            presence = self.presence

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "installation_id": installation_id,
                "hostname": hostname,
                "os": os,
                "last_report_at": last_report_at,
                "presence": presence,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        from ..models.agent_inventory_presence import AgentInventoryPresence

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

        def _parse_presence(data: object) -> AgentInventoryPresence | None:
            if data is None:
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                presence_type_0 = AgentInventoryPresence.from_dict(data)

                return presence_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(AgentInventoryPresence | None, data)

        presence = _parse_presence(d.pop("presence"))

        agent_inventory_user_machine = cls(
            installation_id=installation_id,
            hostname=hostname,
            os=os,
            last_report_at=last_report_at,
            presence=presence,
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
