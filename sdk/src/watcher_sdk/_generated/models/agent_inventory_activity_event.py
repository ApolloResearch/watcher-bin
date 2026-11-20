from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import Any, Self, TypeVar, cast
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.agent_inventory_activity_event_gap_cause_type_0 import (
    AgentInventoryActivityEventGapCauseType0,
)
from ..models.agent_inventory_activity_event_kind import AgentInventoryActivityEventKind
from ..models.agent_inventory_activity_event_signed_off_with_type_0 import (
    AgentInventoryActivityEventSignedOffWithType0,
)
from ..types import UNSET, Unset

T = TypeVar("T", bound="AgentInventoryActivityEvent")


@_attrs_define
class AgentInventoryActivityEvent:
    """One change on one machine, found by comparing the reports its Watcher client sent one after another.

    The reports say what changed on the machine, never who changed it.

        Attributes:
            installation_id (UUID):
            hostname (None | str): The machine's hostname from its newest agent inventory scan in the last 90 days; null
                when there is none, as with inventory off.
            user_id (None | UUID): The machine's owner. Always set today; typed nullable for later kinds.
            user_name (None | str): The owner's name, when Watcher knows it.
            user_email (None | str): Hidden unless you may read other people's email addresses.
            kind (AgentInventoryActivityEventKind): What changed: `went_offline`, in a single machine's feed only, when the
                client stopped checking in: an ongoing silence once its newest report is older than its on-time window (35
                minutes for a client sending the heartbeat, else 75), and a past silence when it lasted longer than 12 hours. A
                past silence of a client that sends no heartbeat can be a time when agent inventory was off. `client_updated`
                when the Watcher client's version changed, an event that never holds; `agent_turned_off` and `agent_turned_on`
                when an agent was turned off or on in Watcher's settings on the machine (an agent turned off that is not on the
                machine is not listed); `hooks_missing` when a turned-on agent's Watcher hooks became missing, whether they were
                installed before, the agent was installed since, or it was turned on without them; `hooks_not_running` when a
                turned-on agent's Watcher hooks were in place but the agent would not run them, with the reason in `to_value`;
                `hooks_restored` when the hooks were back in place and running after either; `snooze_started` and `snooze_ended`
                for a snooze of grading; `mode_changed` when the enforcement mode changed; `uploads_backing_up` when the oldest
                decision waiting to upload became older than 30 minutes, a decision gave up, or more than 100 records of
                ungraded calls were waiting, and `uploads_caught_up` when none of those held any more; `setup_outdated` when a
                turned-on agent's Watcher setup (hooks installed) became older than the client's, and `setup_updated` when it
                was current again; `self_check_flagged` when the client's background self-check's worst result became a warning
                or an error, and `self_check_cleared` when every section was ok again; `inventory_stopped` when inventory scans
                stopped for more than 24 hours while heartbeats kept arriving (an ongoing stop is listed only while collection
                is on), and `inventory_resumed` when scans came back; `health_incomplete` when a health reading had a value the
                client couldn't read (mode, snooze, upload counts, agents, or a turned-on agent's hooks or setup) and
                `health_complete` when one was complete again; `health_missing` when heartbeats arrived without endpoint health,
                two or more in a row, and `health_resumed` when health arrived again.
            at (datetime.datetime): When it happened. For `went_offline`, the last report before it went offline; for
                `inventory_stopped`, the last scan before it; for `inventory_resumed`, the first scan after it; for
                `client_updated`, when the first report with the new version arrived; for an agent or its hooks, when the
                machine first saw the new state if it said so, else when the machine read it; for `snooze_started`, when the
                snooze began; for `snooze_ended`, when the snooze reached its planned end if that fell between the two reports,
                else when the machine read it ended; for `mode_changed`, `uploads_caught_up`, setup and self-check changes, when
                the machine read the new state (a held pause in the organization-wide feed: the first paused reading after the
                newest reading with another mode); for `uploads_backing_up`, when the oldest decision waiting crossed 30
                minutes, which in the organization-wide feed is the oldest one still waiting. In a single machine's feed an
                ongoing silence keeps its true start, however old, so `at` can be earlier than `since`. Any other state that
                began before the 7 days is not listed; the machine's `health` has it.
            agent (None | str): The agent's ID for agent and hook changes; null for every other kind.
            from_value (None | str): The previous client version for `client_updated`, the previous mode for `mode_changed`,
                the previous worst self-check result (`ok`, `warning` or `error`) for the self-check kinds; else null.
            to_value (None | str): The new client version for `client_updated`, the new mode for `mode_changed`, the new
                worst self-check result for the self-check kinds, and for `hooks_not_running` why the agent skips the hooks:
                `untrusted` or `turned_off_in_agent`, as the machine's `health` reports them; else null.
            ended_at (datetime.datetime | None): For `went_offline`, when reports resumed; null while the client is still
                offline, and for every other kind.
            snooze_until (datetime.datetime | None): For `snooze_started`, when the snooze was set to end, which can be in
                the future; null when it had no end, and for every other kind. A snooze cancelled early has its own
                `snooze_ended`.
            locked (bool | None): For `agent_turned_off`, whether the organization's settings lock the agent off, as the
                machine's newest report says while the agent is still off (else as the report beside the change said). It is the
                lock state, not who turned the agent off. Null when the machine could not tell, and for every other kind.
            still_current (bool): Whether the state this change began still holds in the machine's newest report: the agent
                is still off, the snooze still active and not past its planned end, the client still silent, and so on. False
                when a later change undid it, the newest report does not say, and always for `client_updated`.
            signed_off_with (AgentInventoryActivityEventSignedOffWithType0 | None | Unset): For `went_offline`, the event
                the client sent with its last report before it went offline (see the machine's `presence.last_event`); null when
                it sent a scheduled report, and for every other kind.
            gap_cause (AgentInventoryActivityEventGapCauseType0 | None | Unset): For a past `went_offline`, what the first
                report after it came back says about it: `asleep` (the machine slept during the gap), `machine_restarted` (it
                booted during the gap, so it was off or restarting), `watcher_not_running` (the machine stayed up but Watcher's
                process started during the gap) or `not_delivered` (Watcher ran and the machine stayed awake, so its reports
                were sent but did not arrive: a network or server problem). Null while the silence lasts, when the client does
                not report these times, and for every other kind.
    """

    installation_id: UUID
    hostname: None | str
    user_id: None | UUID
    user_name: None | str
    user_email: None | str
    kind: AgentInventoryActivityEventKind
    at: datetime.datetime
    agent: None | str
    from_value: None | str
    to_value: None | str
    ended_at: datetime.datetime | None
    snooze_until: datetime.datetime | None
    locked: bool | None
    still_current: bool
    signed_off_with: AgentInventoryActivityEventSignedOffWithType0 | None | Unset = (
        UNSET
    )
    gap_cause: AgentInventoryActivityEventGapCauseType0 | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        installation_id = str(self.installation_id)

        hostname: None | str
        hostname = self.hostname

        user_id: None | str
        if isinstance(self.user_id, UUID):
            user_id = str(self.user_id)
        else:
            user_id = self.user_id

        user_name: None | str
        user_name = self.user_name

        user_email: None | str
        user_email = self.user_email

        kind = self.kind.value

        at = self.at.isoformat()

        agent: None | str
        agent = self.agent

        from_value: None | str
        from_value = self.from_value

        to_value: None | str
        to_value = self.to_value

        ended_at: None | str
        if isinstance(self.ended_at, datetime.datetime):
            ended_at = self.ended_at.isoformat()
        else:
            ended_at = self.ended_at

        snooze_until: None | str
        if isinstance(self.snooze_until, datetime.datetime):
            snooze_until = self.snooze_until.isoformat()
        else:
            snooze_until = self.snooze_until

        locked: bool | None
        locked = self.locked

        still_current = self.still_current

        signed_off_with: None | str | Unset
        if isinstance(self.signed_off_with, Unset):
            signed_off_with = UNSET
        elif isinstance(
            self.signed_off_with, AgentInventoryActivityEventSignedOffWithType0
        ):
            signed_off_with = self.signed_off_with.value
        else:
            signed_off_with = self.signed_off_with

        gap_cause: None | str | Unset
        if isinstance(self.gap_cause, Unset):
            gap_cause = UNSET
        elif isinstance(self.gap_cause, AgentInventoryActivityEventGapCauseType0):
            gap_cause = self.gap_cause.value
        else:
            gap_cause = self.gap_cause

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "installation_id": installation_id,
                "hostname": hostname,
                "user_id": user_id,
                "user_name": user_name,
                "user_email": user_email,
                "kind": kind,
                "at": at,
                "agent": agent,
                "from_value": from_value,
                "to_value": to_value,
                "ended_at": ended_at,
                "snooze_until": snooze_until,
                "locked": locked,
                "still_current": still_current,
            }
        )
        if signed_off_with is not UNSET:
            field_dict["signed_off_with"] = signed_off_with
        if gap_cause is not UNSET:
            field_dict["gap_cause"] = gap_cause

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

        kind = AgentInventoryActivityEventKind(d.pop("kind"))

        at = datetime.datetime.fromisoformat(d.pop("at"))

        def _parse_agent(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        agent = _parse_agent(d.pop("agent"))

        def _parse_from_value(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        from_value = _parse_from_value(d.pop("from_value"))

        def _parse_to_value(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        to_value = _parse_to_value(d.pop("to_value"))

        def _parse_ended_at(data: object) -> datetime.datetime | None:
            if data is None:
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                ended_at_type_0 = datetime.datetime.fromisoformat(data)

                return ended_at_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None, data)

        ended_at = _parse_ended_at(d.pop("ended_at"))

        def _parse_snooze_until(data: object) -> datetime.datetime | None:
            if data is None:
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                snooze_until_type_0 = datetime.datetime.fromisoformat(data)

                return snooze_until_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None, data)

        snooze_until = _parse_snooze_until(d.pop("snooze_until"))

        def _parse_locked(data: object) -> bool | None:
            if data is None:
                return data
            return cast(bool | None, data)

        locked = _parse_locked(d.pop("locked"))

        still_current = d.pop("still_current")

        def _parse_signed_off_with(
            data: object,
        ) -> AgentInventoryActivityEventSignedOffWithType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                signed_off_with_type_0 = AgentInventoryActivityEventSignedOffWithType0(
                    data
                )

                return signed_off_with_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(
                AgentInventoryActivityEventSignedOffWithType0 | None | Unset, data
            )

        signed_off_with = _parse_signed_off_with(d.pop("signed_off_with", UNSET))

        def _parse_gap_cause(
            data: object,
        ) -> AgentInventoryActivityEventGapCauseType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                gap_cause_type_0 = AgentInventoryActivityEventGapCauseType0(data)

                return gap_cause_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(AgentInventoryActivityEventGapCauseType0 | None | Unset, data)

        gap_cause = _parse_gap_cause(d.pop("gap_cause", UNSET))

        agent_inventory_activity_event = cls(
            installation_id=installation_id,
            hostname=hostname,
            user_id=user_id,
            user_name=user_name,
            user_email=user_email,
            kind=kind,
            at=at,
            agent=agent,
            from_value=from_value,
            to_value=to_value,
            ended_at=ended_at,
            snooze_until=snooze_until,
            locked=locked,
            still_current=still_current,
            signed_off_with=signed_off_with,
            gap_cause=gap_cause,
        )

        agent_inventory_activity_event.additional_properties = d
        return agent_inventory_activity_event

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
