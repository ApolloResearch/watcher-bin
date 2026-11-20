from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import Any, Self, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.agent_inventory_presence_last_event_type_0 import (
    AgentInventoryPresenceLastEventType0,
)
from ..models.agent_inventory_presence_state import AgentInventoryPresenceState
from ..types import UNSET, Unset

T = TypeVar("T", bound="AgentInventoryPresence")


@_attrs_define
class AgentInventoryPresence:
    """Whether the machine's Watcher client is online, judged against how often it reports.

    Every report the client sends counts: an hourly agent inventory scan, or the 15-minute status report (the
    heartbeat) from clients that send one.

        Attributes:
            state (AgentInventoryPresenceState): `online` when the last report is on time; `reports_missing` when reports
                stopped but sessions recorded from this machine show activity after the next report was due, so the machine is
                in use; `offline` otherwise: the machine may be asleep, off or without a network (see `last_event` for what the
                client said before going quiet).
            last_seen_at (datetime.datetime): When the newest report of any kind from this machine arrived.
            reports_every_minutes (int): The reporting interval, in minutes, this machine is currently judged against. It
                follows the reports that arrive, so it can change when the client starts or stops sending heartbeats.
            last_machine_session_at (datetime.datetime | None): The latest activity in the last 7 days in the owner's
                sessions recorded with this machine's hostname; null when there is none. Very recent activity does not count
                toward `state` until the client has had time to report, so an `offline` machine can show a session from a few
                minutes ago.
            active_agents (list[str] | Unset): For `reports_missing`, the coding agents (inventory agent IDs, such as
                `claude_code`) whose sessions recorded from this machine were active after `last_seen_at`, sorted; empty for
                every other state. It tells which agents are uploading sessions while the client's reports are missing.
            last_event (AgentInventoryPresenceLastEventType0 | None | Unset): What the client said it was doing in its last
                report, when it sent that report outside its schedule: `going_to_sleep`, `woke`, `stopping` (shutting down,
                restarting, logging out of the OS or updating), `stopped_by_user` or `signing_out`. Null for a scheduled report
                or a client that does not send events. Going offline after `going_to_sleep` or `stopping` is expected; after
                `stopped_by_user` or `signing_out` Watcher is off on the machine until someone starts it or signs in.
            online_until (datetime.datetime | None | Unset): For `online`, when the machine stops counting as online unless
                another report arrives: `last_seen_at` plus the on-time window for `reports_every_minutes` (35 minutes for a
                15-minute client, 75 for an hourly one). Null for every other state. A view kept open past it should show
                `online` as last known.
            may_change_at (datetime.datetime | None | Unset): The first time at which time alone could change `state`, never
                later than the change itself: `online_until` for `online`; for `offline` with sessions from this machine after
                its last report, when those sessions start to count; for `reports_missing`, when its newest session leaves the
                7-day session window. Null when only a new report or session can change it.
    """

    state: AgentInventoryPresenceState
    last_seen_at: datetime.datetime
    reports_every_minutes: int
    last_machine_session_at: datetime.datetime | None
    active_agents: list[str] | Unset = UNSET
    last_event: AgentInventoryPresenceLastEventType0 | None | Unset = UNSET
    online_until: datetime.datetime | None | Unset = UNSET
    may_change_at: datetime.datetime | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        state = self.state.value

        last_seen_at = self.last_seen_at.isoformat()

        reports_every_minutes = self.reports_every_minutes

        last_machine_session_at: None | str
        if isinstance(self.last_machine_session_at, datetime.datetime):
            last_machine_session_at = self.last_machine_session_at.isoformat()
        else:
            last_machine_session_at = self.last_machine_session_at

        active_agents: list[str] | Unset = UNSET
        if not isinstance(self.active_agents, Unset):
            active_agents = self.active_agents

        last_event: None | str | Unset
        if isinstance(self.last_event, Unset):
            last_event = UNSET
        elif isinstance(self.last_event, AgentInventoryPresenceLastEventType0):
            last_event = self.last_event.value
        else:
            last_event = self.last_event

        online_until: None | str | Unset
        if isinstance(self.online_until, Unset):
            online_until = UNSET
        elif isinstance(self.online_until, datetime.datetime):
            online_until = self.online_until.isoformat()
        else:
            online_until = self.online_until

        may_change_at: None | str | Unset
        if isinstance(self.may_change_at, Unset):
            may_change_at = UNSET
        elif isinstance(self.may_change_at, datetime.datetime):
            may_change_at = self.may_change_at.isoformat()
        else:
            may_change_at = self.may_change_at

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "state": state,
                "last_seen_at": last_seen_at,
                "reports_every_minutes": reports_every_minutes,
                "last_machine_session_at": last_machine_session_at,
            }
        )
        if active_agents is not UNSET:
            field_dict["active_agents"] = active_agents
        if last_event is not UNSET:
            field_dict["last_event"] = last_event
        if online_until is not UNSET:
            field_dict["online_until"] = online_until
        if may_change_at is not UNSET:
            field_dict["may_change_at"] = may_change_at

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        d = dict(src_dict)
        state = AgentInventoryPresenceState(d.pop("state"))

        last_seen_at = datetime.datetime.fromisoformat(d.pop("last_seen_at"))

        reports_every_minutes = d.pop("reports_every_minutes")

        def _parse_last_machine_session_at(data: object) -> datetime.datetime | None:
            if data is None:
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                last_machine_session_at_type_0 = datetime.datetime.fromisoformat(data)

                return last_machine_session_at_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None, data)

        last_machine_session_at = _parse_last_machine_session_at(
            d.pop("last_machine_session_at")
        )

        active_agents = cast(list[str], d.pop("active_agents", UNSET))

        def _parse_last_event(
            data: object,
        ) -> AgentInventoryPresenceLastEventType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                last_event_type_0 = AgentInventoryPresenceLastEventType0(data)

                return last_event_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(AgentInventoryPresenceLastEventType0 | None | Unset, data)

        last_event = _parse_last_event(d.pop("last_event", UNSET))

        def _parse_online_until(data: object) -> datetime.datetime | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                online_until_type_0 = datetime.datetime.fromisoformat(data)

                return online_until_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None | Unset, data)

        online_until = _parse_online_until(d.pop("online_until", UNSET))

        def _parse_may_change_at(data: object) -> datetime.datetime | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                may_change_at_type_0 = datetime.datetime.fromisoformat(data)

                return may_change_at_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None | Unset, data)

        may_change_at = _parse_may_change_at(d.pop("may_change_at", UNSET))

        agent_inventory_presence = cls(
            state=state,
            last_seen_at=last_seen_at,
            reports_every_minutes=reports_every_minutes,
            last_machine_session_at=last_machine_session_at,
            active_agents=active_agents,
            last_event=last_event,
            online_until=online_until,
            may_change_at=may_change_at,
        )

        agent_inventory_presence.additional_properties = d
        return agent_inventory_presence

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
