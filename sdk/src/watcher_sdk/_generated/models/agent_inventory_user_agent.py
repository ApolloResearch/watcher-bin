from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import Any, Self, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.agent_inventory_user_agent_coverage_type_0 import (
    AgentInventoryUserAgentCoverageType0,
)
from ..models.agent_inventory_user_agent_coverage_via_type_0 import (
    AgentInventoryUserAgentCoverageViaType0,
)
from ..models.agent_inventory_user_agent_seen_via_type_0 import (
    AgentInventoryUserAgentSeenViaType0,
)
from ..types import UNSET, Unset

T = TypeVar("T", bound="AgentInventoryUserAgent")


@_attrs_define
class AgentInventoryUserAgent:
    """One agent or gateway client a person used in the last 7 days.

    Attributes:
        agent_id (str): The agent ID, or the client name for an unrecognized gateway client.
        recognized (bool): Whether the client is an agent the inventory knows.
        use_detected (bool): Whether the Watcher client can tell when this agent was last used; false for unrecognized
            gateway clients.
        seen_via (AgentInventoryUserAgentSeenViaType0 | None): Where inventory saw the use: on one of their machines, in
            gateway traffic, or both; null when only sessions Watcher received show it.
        last_used_on (datetime.date | None): The latest UTC date the agent was used on one of their machines; null when
            no machine reports it.
        last_seen_at (datetime.datetime | None): When it was last seen in their gateway traffic, if it was.
        versions (list[str]): The distinct versions on the machines where they used it recently.
        coverage (AgentInventoryUserAgentCoverageType0 | None): The person's coverage for this agent; null when it was
            only seen at a gateway and Watcher received no session for it.
        coverage_via (AgentInventoryUserAgentCoverageViaType0 | None): When `coverage` is `monitored`, how Watcher
            received their sessions: `client`, `gateway` or `both`; null otherwise.
        watcher_hooks (list[str]): The distinct Watcher hook states on the machines where they used it recently: `on`,
            `off`, `disabled` or `not_applicable`. Explains a gap.
        watcher_sessions (int | None | Unset): The person's Watcher sessions for this agent active in the last 7 days,
            from any of their machines or a gateway; null when Watcher cannot receive sessions from the agent.
        last_session_at (datetime.datetime | None | Unset): The person's newest Watcher session for this agent, of any
            age.
    """

    agent_id: str
    recognized: bool
    use_detected: bool
    seen_via: AgentInventoryUserAgentSeenViaType0 | None
    last_used_on: datetime.date | None
    last_seen_at: datetime.datetime | None
    versions: list[str]
    coverage: AgentInventoryUserAgentCoverageType0 | None
    coverage_via: AgentInventoryUserAgentCoverageViaType0 | None
    watcher_hooks: list[str]
    watcher_sessions: int | None | Unset = UNSET
    last_session_at: datetime.datetime | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        agent_id = self.agent_id

        recognized = self.recognized

        use_detected = self.use_detected

        seen_via: None | str
        if isinstance(self.seen_via, AgentInventoryUserAgentSeenViaType0):
            seen_via = self.seen_via.value
        else:
            seen_via = self.seen_via

        last_used_on: None | str
        if isinstance(self.last_used_on, datetime.date):
            last_used_on = self.last_used_on.isoformat()
        else:
            last_used_on = self.last_used_on

        last_seen_at: None | str
        if isinstance(self.last_seen_at, datetime.datetime):
            last_seen_at = self.last_seen_at.isoformat()
        else:
            last_seen_at = self.last_seen_at

        versions = self.versions

        coverage: None | str
        if isinstance(self.coverage, AgentInventoryUserAgentCoverageType0):
            coverage = self.coverage.value
        else:
            coverage = self.coverage

        coverage_via: None | str
        if isinstance(self.coverage_via, AgentInventoryUserAgentCoverageViaType0):
            coverage_via = self.coverage_via.value
        else:
            coverage_via = self.coverage_via

        watcher_hooks = self.watcher_hooks

        watcher_sessions: int | None | Unset
        if isinstance(self.watcher_sessions, Unset):
            watcher_sessions = UNSET
        else:
            watcher_sessions = self.watcher_sessions

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
                "recognized": recognized,
                "use_detected": use_detected,
                "seen_via": seen_via,
                "last_used_on": last_used_on,
                "last_seen_at": last_seen_at,
                "versions": versions,
                "coverage": coverage,
                "coverage_via": coverage_via,
                "watcher_hooks": watcher_hooks,
            }
        )
        if watcher_sessions is not UNSET:
            field_dict["watcher_sessions"] = watcher_sessions
        if last_session_at is not UNSET:
            field_dict["last_session_at"] = last_session_at

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        d = dict(src_dict)
        agent_id = d.pop("agent_id")

        recognized = d.pop("recognized")

        use_detected = d.pop("use_detected")

        def _parse_seen_via(data: object) -> AgentInventoryUserAgentSeenViaType0 | None:
            if data is None:
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                seen_via_type_0 = AgentInventoryUserAgentSeenViaType0(data)

                return seen_via_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(AgentInventoryUserAgentSeenViaType0 | None, data)

        seen_via = _parse_seen_via(d.pop("seen_via"))

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

        def _parse_last_seen_at(data: object) -> datetime.datetime | None:
            if data is None:
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                last_seen_at_type_0 = datetime.datetime.fromisoformat(data)

                return last_seen_at_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None, data)

        last_seen_at = _parse_last_seen_at(d.pop("last_seen_at"))

        versions = cast(list[str], d.pop("versions"))

        def _parse_coverage(
            data: object,
        ) -> AgentInventoryUserAgentCoverageType0 | None:
            if data is None:
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                coverage_type_0 = AgentInventoryUserAgentCoverageType0(data)

                return coverage_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(AgentInventoryUserAgentCoverageType0 | None, data)

        coverage = _parse_coverage(d.pop("coverage"))

        def _parse_coverage_via(
            data: object,
        ) -> AgentInventoryUserAgentCoverageViaType0 | None:
            if data is None:
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                coverage_via_type_0 = AgentInventoryUserAgentCoverageViaType0(data)

                return coverage_via_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(AgentInventoryUserAgentCoverageViaType0 | None, data)

        coverage_via = _parse_coverage_via(d.pop("coverage_via"))

        watcher_hooks = cast(list[str], d.pop("watcher_hooks"))

        def _parse_watcher_sessions(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        watcher_sessions = _parse_watcher_sessions(d.pop("watcher_sessions", UNSET))

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

        agent_inventory_user_agent = cls(
            agent_id=agent_id,
            recognized=recognized,
            use_detected=use_detected,
            seen_via=seen_via,
            last_used_on=last_used_on,
            last_seen_at=last_seen_at,
            versions=versions,
            coverage=coverage,
            coverage_via=coverage_via,
            watcher_hooks=watcher_hooks,
            watcher_sessions=watcher_sessions,
            last_session_at=last_session_at,
        )

        agent_inventory_user_agent.additional_properties = d
        return agent_inventory_user_agent

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
