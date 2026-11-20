from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Self, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.agent_inventory_health_condition_cause_type_0 import (
    AgentInventoryHealthConditionCauseType0,
)
from ..models.agent_inventory_health_condition_code import (
    AgentInventoryHealthConditionCode,
)
from ..models.agent_inventory_health_condition_reasons_item import (
    AgentInventoryHealthConditionReasonsItem,
)
from ..models.agent_inventory_health_condition_severity import (
    AgentInventoryHealthConditionSeverity,
)
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.agent_inventory_self_check_finding import (
        AgentInventorySelfCheckFinding,
    )
    from ..models.agent_inventory_unread_value import AgentInventoryUnreadValue


T = TypeVar("T", bound="AgentInventoryHealthCondition")


@_attrs_define
class AgentInventoryHealthCondition:
    """One thing worth knowing about a machine's health, judged when the machine list was read.

    It names the condition and the evidence behind it, never the words to show: a reader words it from `code` and
    the machine's own fields.

        Attributes:
            code (AgentInventoryHealthConditionCode): What the condition is. Check-in: `reports_missing` (sessions kept
                arriving after reports stopped), `watcher_stopped`, `signed_out`, `offline_long` (offline 7 days or more),
                `asleep`, `shut_down`, `offline` (no reason given), `not_reporting` (agent inventory is off and the client sends
                no status report, so whether it is online cannot be judged). Health: `no_health`, `health_stale` (the newest
                reading of an online machine is older than one heartbeat window), `agent_off`, `agent_locked_off` (the
                organization's settings disable the agent), `hooks_missing`, `hooks_untrusted`, `hooks_turned_off_in_agent`,
                `setup_outdated`, `paused`, `observe`, `snoozed`, `uploads` (uploads backing up), `self_check`,
                `health_incomplete`. Inventory: `sessions_missing` (an agent with Watcher's hooks was used on the machine but
                none of its sessions arrived), `unmonitored_agents` (an agent without hooks was used and Watcher received none
                of its owner's sessions for it), `no_inventory`, `inventory_stale`. Values may be added.
            severity (AgentInventoryHealthConditionSeverity): `problem` or `warning` for something to act on; `note` for
                something worth knowing that needs no action: an expected offline state, observe mode, an agent the organization
                disables, a snooze that has ended or agents only a gateway could monitor.
            agent (None | str | Unset): The agent ID, for a condition about one agent's health (`agent_off`,
                `agent_locked_off`, the `hooks_*` codes and `setup_outdated`); its entry in `health.agents` holds the detail.
                Null otherwise.
            agents (list[str] | Unset): For `sessions_missing` and `unmonitored_agents`, the agent IDs concerned; empty
                otherwise.
            since (datetime.datetime | None | Unset): When the condition began, when the evidence shows it: the last check-
                in for a check-in condition, an agent's `since`, a snooze's start, the oldest decision waiting, the health
                reading's arrival for `health_stale`, the scan for `inventory_stale`. Null when unknown.
            expires_at (datetime.datetime | None | Unset): When time alone ends or changes this condition: the end of a
                snooze, the 7 days after which an offline machine needs attention, the day after a scan that sessions are
                matched against. Null when only a new report or session can change it.
            last_known (bool | Unset): Read from a health reading that is no longer current (the machine is not online, or
                the reading is older than one heartbeat window), so it may have changed since. Default: False.
            cause (AgentInventoryHealthConditionCauseType0 | None | Unset): Why, for a code with more than one cause.
                `no_health`: `client_too_old` (it sends only hourly scans) or `health_read_failing` (it sends heartbeats without
                health). `reports_missing`: `watcher_running` (sessions from an agent whose hooks upload only while the Watcher
                app runs and is signed in, so the reports are not reaching the server) or `watcher_may_have_stopped`. Null
                otherwise.
            sections (list[AgentInventorySelfCheckFinding] | Unset): For `self_check`, the flagged sections in `watcher
                doctor` order, leaving out those another condition already explains (`hooks` beside an agent's hooks condition,
                `decisions` beside `uploads`, `enforcement` beside `paused`); empty otherwise.
            unread (list[AgentInventoryUnreadValue] | Unset): For `health_incomplete`, each value the machine could not
                read.
            reasons (list[AgentInventoryHealthConditionReasonsItem] | Unset): For `uploads`, why: `waiting` (decisions
                waiting that the machine's decisions self-check flagged), `gave_up` (decisions it stopped retrying) or
                `call_records` (more than 100 records of ungraded calls waiting). Empty otherwise.
    """

    code: AgentInventoryHealthConditionCode
    severity: AgentInventoryHealthConditionSeverity
    agent: None | str | Unset = UNSET
    agents: list[str] | Unset = UNSET
    since: datetime.datetime | None | Unset = UNSET
    expires_at: datetime.datetime | None | Unset = UNSET
    last_known: bool | Unset = False
    cause: AgentInventoryHealthConditionCauseType0 | None | Unset = UNSET
    sections: list[AgentInventorySelfCheckFinding] | Unset = UNSET
    unread: list[AgentInventoryUnreadValue] | Unset = UNSET
    reasons: list[AgentInventoryHealthConditionReasonsItem] | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        code = self.code.value

        severity = self.severity.value

        agent: None | str | Unset
        if isinstance(self.agent, Unset):
            agent = UNSET
        else:
            agent = self.agent

        agents: list[str] | Unset = UNSET
        if not isinstance(self.agents, Unset):
            agents = self.agents

        since: None | str | Unset
        if isinstance(self.since, Unset):
            since = UNSET
        elif isinstance(self.since, datetime.datetime):
            since = self.since.isoformat()
        else:
            since = self.since

        expires_at: None | str | Unset
        if isinstance(self.expires_at, Unset):
            expires_at = UNSET
        elif isinstance(self.expires_at, datetime.datetime):
            expires_at = self.expires_at.isoformat()
        else:
            expires_at = self.expires_at

        last_known = self.last_known

        cause: None | str | Unset
        if isinstance(self.cause, Unset):
            cause = UNSET
        elif isinstance(self.cause, AgentInventoryHealthConditionCauseType0):
            cause = self.cause.value
        else:
            cause = self.cause

        sections: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.sections, Unset):
            sections = []
            for sections_item_data in self.sections:
                sections_item = sections_item_data.to_dict()
                sections.append(sections_item)

        unread: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.unread, Unset):
            unread = []
            for unread_item_data in self.unread:
                unread_item = unread_item_data.to_dict()
                unread.append(unread_item)

        reasons: list[str] | Unset = UNSET
        if not isinstance(self.reasons, Unset):
            reasons = []
            for reasons_item_data in self.reasons:
                reasons_item = reasons_item_data.value
                reasons.append(reasons_item)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "code": code,
                "severity": severity,
            }
        )
        if agent is not UNSET:
            field_dict["agent"] = agent
        if agents is not UNSET:
            field_dict["agents"] = agents
        if since is not UNSET:
            field_dict["since"] = since
        if expires_at is not UNSET:
            field_dict["expires_at"] = expires_at
        if last_known is not UNSET:
            field_dict["last_known"] = last_known
        if cause is not UNSET:
            field_dict["cause"] = cause
        if sections is not UNSET:
            field_dict["sections"] = sections
        if unread is not UNSET:
            field_dict["unread"] = unread
        if reasons is not UNSET:
            field_dict["reasons"] = reasons

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        from ..models.agent_inventory_self_check_finding import (
            AgentInventorySelfCheckFinding,
        )
        from ..models.agent_inventory_unread_value import AgentInventoryUnreadValue

        d = dict(src_dict)
        code = AgentInventoryHealthConditionCode(d.pop("code"))

        severity = AgentInventoryHealthConditionSeverity(d.pop("severity"))

        def _parse_agent(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        agent = _parse_agent(d.pop("agent", UNSET))

        agents = cast(list[str], d.pop("agents", UNSET))

        def _parse_since(data: object) -> datetime.datetime | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                since_type_0 = datetime.datetime.fromisoformat(data)

                return since_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None | Unset, data)

        since = _parse_since(d.pop("since", UNSET))

        def _parse_expires_at(data: object) -> datetime.datetime | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                expires_at_type_0 = datetime.datetime.fromisoformat(data)

                return expires_at_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None | Unset, data)

        expires_at = _parse_expires_at(d.pop("expires_at", UNSET))

        last_known = d.pop("last_known", UNSET)

        def _parse_cause(
            data: object,
        ) -> AgentInventoryHealthConditionCauseType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                cause_type_0 = AgentInventoryHealthConditionCauseType0(data)

                return cause_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(AgentInventoryHealthConditionCauseType0 | None | Unset, data)

        cause = _parse_cause(d.pop("cause", UNSET))

        _sections = d.pop("sections", UNSET)
        sections: list[AgentInventorySelfCheckFinding] | Unset = UNSET
        if _sections is not UNSET:
            sections = []
            for sections_item_data in _sections:
                sections_item = AgentInventorySelfCheckFinding.from_dict(
                    sections_item_data
                )

                sections.append(sections_item)

        _unread = d.pop("unread", UNSET)
        unread: list[AgentInventoryUnreadValue] | Unset = UNSET
        if _unread is not UNSET:
            unread = []
            for unread_item_data in _unread:
                unread_item = AgentInventoryUnreadValue.from_dict(unread_item_data)

                unread.append(unread_item)

        _reasons = d.pop("reasons", UNSET)
        reasons: list[AgentInventoryHealthConditionReasonsItem] | Unset = UNSET
        if _reasons is not UNSET:
            reasons = []
            for reasons_item_data in _reasons:
                reasons_item = AgentInventoryHealthConditionReasonsItem(
                    reasons_item_data
                )

                reasons.append(reasons_item)

        agent_inventory_health_condition = cls(
            code=code,
            severity=severity,
            agent=agent,
            agents=agents,
            since=since,
            expires_at=expires_at,
            last_known=last_known,
            cause=cause,
            sections=sections,
            unread=unread,
            reasons=reasons,
        )

        agent_inventory_health_condition.additional_properties = d
        return agent_inventory_health_condition

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
