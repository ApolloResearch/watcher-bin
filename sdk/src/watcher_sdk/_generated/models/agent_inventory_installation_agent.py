from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import Any, Self, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.agent_inventory_installation_agent_coverage_type_0 import (
    AgentInventoryInstallationAgentCoverageType0,
)
from ..models.agent_inventory_installation_agent_coverage_via_type_0 import (
    AgentInventoryInstallationAgentCoverageViaType0,
)
from ..types import UNSET, Unset

T = TypeVar("T", bound="AgentInventoryInstallationAgent")


@_attrs_define
class AgentInventoryInstallationAgent:
    """One agent on one machine.

    Attributes:
        agent_id (str):
        supported (bool):
        use_detected (bool): Whether the Watcher client can tell when this agent was last used.
        surfaces (list[str]):
        version (None | str):
        last_used_on (datetime.date | None): The UTC date the agent was last used.
        recent_sessions (int | None): Session files modified in the last 7 days, when countable.
        watcher_hooks (str): Whether Watcher's hooks are set up for this agent on this machine: `on`; `off` when the
            agent is turned on in Watcher but its hooks are not installed; `disabled` when the agent is turned off in
            Watcher; or `not_applicable` when Watcher has no hooks for it.
        settings_folder_only (bool): True when the only trace of the agent on this machine is its settings folder.
        coverage (AgentInventoryInstallationAgentCoverageType0 | None): The owner's coverage for this agent; null when
            neither this machine nor Watcher's sessions show use in the last 7 days.
        coverage_via (AgentInventoryInstallationAgentCoverageViaType0 | None): When `coverage` is `monitored`, how
            Watcher received the owner's sessions for this agent in the last 7 days: `client` through the Watcher client,
            `gateway` through a gateway or another API integration, or `both`. Null for any other coverage, or when the
            sessions do not record how they arrived.
        watcher_sessions (int | None | Unset): The owner's Watcher sessions for this agent active in the last 7 days,
            from any of their machines or a gateway; null when Watcher cannot receive sessions from the agent.
        machine_watcher_sessions (int | None | Unset): The owner's Watcher sessions for this agent active in the last 7
            days recorded with this machine's hostname, matched as the session list's machine filter matches. Sessions with
            no recorded hostname, such as those through a gateway or SDK, are not counted, and the owner's machines with the
            same hostname share the count. Null when Watcher cannot receive sessions from the agent or the machine reported
            no hostname.
        last_session_at (datetime.datetime | None | Unset): The owner's newest Watcher session for this agent, of any
            age.
    """

    agent_id: str
    supported: bool
    use_detected: bool
    surfaces: list[str]
    version: None | str
    last_used_on: datetime.date | None
    recent_sessions: int | None
    watcher_hooks: str
    settings_folder_only: bool
    coverage: AgentInventoryInstallationAgentCoverageType0 | None
    coverage_via: AgentInventoryInstallationAgentCoverageViaType0 | None
    watcher_sessions: int | None | Unset = UNSET
    machine_watcher_sessions: int | None | Unset = UNSET
    last_session_at: datetime.datetime | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        agent_id = self.agent_id

        supported = self.supported

        use_detected = self.use_detected

        surfaces = self.surfaces

        version: None | str
        version = self.version

        last_used_on: None | str
        if isinstance(self.last_used_on, datetime.date):
            last_used_on = self.last_used_on.isoformat()
        else:
            last_used_on = self.last_used_on

        recent_sessions: int | None
        recent_sessions = self.recent_sessions

        watcher_hooks = self.watcher_hooks

        settings_folder_only = self.settings_folder_only

        coverage: None | str
        if isinstance(self.coverage, AgentInventoryInstallationAgentCoverageType0):
            coverage = self.coverage.value
        else:
            coverage = self.coverage

        coverage_via: None | str
        if isinstance(
            self.coverage_via, AgentInventoryInstallationAgentCoverageViaType0
        ):
            coverage_via = self.coverage_via.value
        else:
            coverage_via = self.coverage_via

        watcher_sessions: int | None | Unset
        if isinstance(self.watcher_sessions, Unset):
            watcher_sessions = UNSET
        else:
            watcher_sessions = self.watcher_sessions

        machine_watcher_sessions: int | None | Unset
        if isinstance(self.machine_watcher_sessions, Unset):
            machine_watcher_sessions = UNSET
        else:
            machine_watcher_sessions = self.machine_watcher_sessions

        last_session_at: None | str | Unset
        if isinstance(self.last_session_at, Unset):
            last_session_at = UNSET
        elif isinstance(self.last_session_at, datetime.datetime):
            last_session_at = self.last_session_at.isoformat()
        else:
            last_session_at = self.last_session_at

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "agent_id": agent_id,
                "supported": supported,
                "use_detected": use_detected,
                "surfaces": surfaces,
                "version": version,
                "last_used_on": last_used_on,
                "recent_sessions": recent_sessions,
                "watcher_hooks": watcher_hooks,
                "settings_folder_only": settings_folder_only,
                "coverage": coverage,
                "coverage_via": coverage_via,
            }
        )
        if watcher_sessions is not UNSET:
            field_dict["watcher_sessions"] = watcher_sessions
        if machine_watcher_sessions is not UNSET:
            field_dict["machine_watcher_sessions"] = machine_watcher_sessions
        if last_session_at is not UNSET:
            field_dict["last_session_at"] = last_session_at

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        d = dict(src_dict)
        agent_id = d.pop("agent_id")

        supported = d.pop("supported")

        use_detected = d.pop("use_detected")

        surfaces = cast(list[str], d.pop("surfaces"))

        def _parse_version(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        version = _parse_version(d.pop("version"))

        def _parse_last_used_on(data: object) -> datetime.date | None:
            if data is None:
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                last_used_on_type_0 = datetime.date.fromisoformat(data)

                return last_used_on_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.date | None, data)

        last_used_on = _parse_last_used_on(d.pop("last_used_on"))

        def _parse_recent_sessions(data: object) -> int | None:
            if data is None:
                return data
            return cast(int | None, data)

        recent_sessions = _parse_recent_sessions(d.pop("recent_sessions"))

        watcher_hooks = d.pop("watcher_hooks")

        settings_folder_only = d.pop("settings_folder_only")

        def _parse_coverage(
            data: object,
        ) -> AgentInventoryInstallationAgentCoverageType0 | None:
            if data is None:
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                coverage_type_0 = AgentInventoryInstallationAgentCoverageType0(data)

                return coverage_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(AgentInventoryInstallationAgentCoverageType0 | None, data)

        coverage = _parse_coverage(d.pop("coverage"))

        def _parse_coverage_via(
            data: object,
        ) -> AgentInventoryInstallationAgentCoverageViaType0 | None:
            if data is None:
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                coverage_via_type_0 = AgentInventoryInstallationAgentCoverageViaType0(
                    data
                )

                return coverage_via_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(AgentInventoryInstallationAgentCoverageViaType0 | None, data)

        coverage_via = _parse_coverage_via(d.pop("coverage_via"))

        def _parse_watcher_sessions(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        watcher_sessions = _parse_watcher_sessions(d.pop("watcher_sessions", UNSET))

        def _parse_machine_watcher_sessions(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        machine_watcher_sessions = _parse_machine_watcher_sessions(
            d.pop("machine_watcher_sessions", UNSET)
        )

        def _parse_last_session_at(data: object) -> datetime.datetime | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                last_session_at_type_0 = datetime.datetime.fromisoformat(data)

                return last_session_at_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None | Unset, data)

        last_session_at = _parse_last_session_at(d.pop("last_session_at", UNSET))

        agent_inventory_installation_agent = cls(
            agent_id=agent_id,
            supported=supported,
            use_detected=use_detected,
            surfaces=surfaces,
            version=version,
            last_used_on=last_used_on,
            recent_sessions=recent_sessions,
            watcher_hooks=watcher_hooks,
            settings_folder_only=settings_folder_only,
            coverage=coverage,
            coverage_via=coverage_via,
            watcher_sessions=watcher_sessions,
            machine_watcher_sessions=machine_watcher_sessions,
            last_session_at=last_session_at,
        )

        agent_inventory_installation_agent.additional_properties = d
        return agent_inventory_installation_agent

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
