from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Self, TypeVar, cast
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.agent_inventory_health import AgentInventoryHealth
    from ..models.agent_inventory_health_assessment import (
        AgentInventoryHealthAssessment,
    )
    from ..models.agent_inventory_installation_agent import (
        AgentInventoryInstallationAgent,
    )
    from ..models.agent_inventory_installation_owner_watcher_sessions import (
        AgentInventoryInstallationOwnerWatcherSessions,
    )
    from ..models.agent_inventory_missed_calls import AgentInventoryMissedCalls
    from ..models.agent_inventory_presence import AgentInventoryPresence


T = TypeVar("T", bound="AgentInventoryInstallation")


@_attrs_define
class AgentInventoryInstallation:
    """One machine running the Watcher client, with its owner and agents.

    A machine is listed while its newest report of any kind, its 15-minute heartbeat included, is from the last 90
    days, so machines show with agent inventory off too. A machine with no inventory scan in the last 90 days has
    null `hostname`, `os`, `arch` and `inventory_reported_at`, and no agents: inventory was not collected from it.

        Attributes:
            installation_id (UUID):
            user_id (None | UUID):
            user_name (None | str):
            user_email (None | str): Hidden unless you may read other people's email addresses.
            hostname (None | str): From the newest inventory scan; null when none was collected.
            os (None | str): From the newest inventory scan; null when none was collected.
            arch (None | str): From the newest inventory scan; null when none was collected.
            client_version (None | str): The Watcher client's version from the newest report, a heartbeat or an inventory
                scan; when that report has none, from the newest inventory scan.
            first_report_at (datetime.datetime): When the machine first sent any report, usually a heartbeat, so it can
                predate its first inventory report.
            last_report_at (datetime.datetime): When the newest report of any kind from this machine arrived. When
                `presence` is present, its `last_seen_at` is this time.
            inventory_reported_at (datetime.datetime | None): When the newest report with this machine's agents (an
                inventory scan) arrived; null when none arrived in the last 90 days.
            presence (AgentInventoryPresence | None): Whether the machine's Watcher client is online; null while agent
                inventory is off and the client sends no heartbeat, because no new report from it is stored and whether it is
                online cannot be judged.
            health (AgentInventoryHealth | None): Snooze, agents turned off, enforcement mode, upload backlog and self-
                check: the newest values among the machine's 10 most recent reports of any kind. Null when none of those 10
                carried them (a client too old to send them, or one whose health read kept failing) or the stored value could
                not be read.
            missed_calls (AgentInventoryMissedCalls): Tool calls the machine's Watcher client observed but did not grade in
                the last 7 days, by reason.

                Counted from the metadata-only tool-call records the client sent naming this installation: counts only, never
                tool names, IDs or content. A call graded after all (its record was replaced by an evaluation) is not counted.
            agents (list[AgentInventoryInstallationAgent]):
            assessment (AgentInventoryHealthAssessment): What Watcher makes of the machine's check-in, health and inventory,
                judged when the list was read.

                The rules behind it live on the server only. Judged at one instant, it can go out of date while it is shown:
                once `expires_at` passes, show it as last known rather than working out a new one.
            owner_watcher_sessions (AgentInventoryInstallationOwnerWatcherSessions | Unset): The owner's Watcher sessions
                active in the last 7 days, per agent Watcher can receive sessions from, from any of their machines or a gateway;
                an agent with none is left out. It stands in for the agents' own counts on a machine with no inventory scan,
                whose sessions cannot be matched to it by hostname.
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
    inventory_reported_at: datetime.datetime | None
    presence: AgentInventoryPresence | None
    health: AgentInventoryHealth | None
    missed_calls: AgentInventoryMissedCalls
    agents: list[AgentInventoryInstallationAgent]
    assessment: AgentInventoryHealthAssessment
    owner_watcher_sessions: AgentInventoryInstallationOwnerWatcherSessions | Unset = (
        UNSET
    )
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.agent_inventory_health import AgentInventoryHealth
        from ..models.agent_inventory_presence import AgentInventoryPresence

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

        inventory_reported_at: None | str
        if isinstance(self.inventory_reported_at, datetime.datetime):
            inventory_reported_at = self.inventory_reported_at.isoformat()
        else:
            inventory_reported_at = self.inventory_reported_at

        presence: dict[str, Any] | None
        if isinstance(self.presence, AgentInventoryPresence):
            presence = self.presence.to_dict()
        else:
            presence = self.presence

        health: dict[str, Any] | None
        if isinstance(self.health, AgentInventoryHealth):
            health = self.health.to_dict()
        else:
            health = self.health

        missed_calls = self.missed_calls.to_dict()

        agents = []
        for agents_item_data in self.agents:
            agents_item = agents_item_data.to_dict()
            agents.append(agents_item)

        assessment = self.assessment.to_dict()

        owner_watcher_sessions: dict[str, Any] | Unset = UNSET
        if not isinstance(self.owner_watcher_sessions, Unset):
            owner_watcher_sessions = self.owner_watcher_sessions.to_dict()

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
                "inventory_reported_at": inventory_reported_at,
                "presence": presence,
                "health": health,
                "missed_calls": missed_calls,
                "agents": agents,
                "assessment": assessment,
            }
        )
        if owner_watcher_sessions is not UNSET:
            field_dict["owner_watcher_sessions"] = owner_watcher_sessions

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        from ..models.agent_inventory_health import AgentInventoryHealth
        from ..models.agent_inventory_health_assessment import (
            AgentInventoryHealthAssessment,
        )
        from ..models.agent_inventory_installation_agent import (
            AgentInventoryInstallationAgent,
        )
        from ..models.agent_inventory_installation_owner_watcher_sessions import (
            AgentInventoryInstallationOwnerWatcherSessions,
        )
        from ..models.agent_inventory_missed_calls import AgentInventoryMissedCalls
        from ..models.agent_inventory_presence import AgentInventoryPresence

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

        def _parse_inventory_reported_at(data: object) -> datetime.datetime | None:
            if data is None:
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                inventory_reported_at_type_0 = datetime.datetime.fromisoformat(data)

                return inventory_reported_at_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None, data)

        inventory_reported_at = _parse_inventory_reported_at(
            d.pop("inventory_reported_at")
        )

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

        def _parse_health(data: object) -> AgentInventoryHealth | None:
            if data is None:
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                health_type_0 = AgentInventoryHealth.from_dict(data)

                return health_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(AgentInventoryHealth | None, data)

        health = _parse_health(d.pop("health"))

        missed_calls = AgentInventoryMissedCalls.from_dict(d.pop("missed_calls"))

        agents = []
        _agents = d.pop("agents")
        for agents_item_data in _agents:
            agents_item = AgentInventoryInstallationAgent.from_dict(agents_item_data)

            agents.append(agents_item)

        assessment = AgentInventoryHealthAssessment.from_dict(d.pop("assessment"))

        _owner_watcher_sessions = d.pop("owner_watcher_sessions", UNSET)
        owner_watcher_sessions: AgentInventoryInstallationOwnerWatcherSessions | Unset
        if isinstance(_owner_watcher_sessions, Unset):
            owner_watcher_sessions = UNSET
        else:
            owner_watcher_sessions = (
                AgentInventoryInstallationOwnerWatcherSessions.from_dict(
                    _owner_watcher_sessions
                )
            )

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
            inventory_reported_at=inventory_reported_at,
            presence=presence,
            health=health,
            missed_calls=missed_calls,
            agents=agents,
            assessment=assessment,
            owner_watcher_sessions=owner_watcher_sessions,
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
