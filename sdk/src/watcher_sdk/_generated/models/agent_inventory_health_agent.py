from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import Any, Self, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="AgentInventoryHealthAgent")


@_attrs_define
class AgentInventoryHealthAgent:
    """One coding agent Watcher has hooks for, as the machine reported it.

    Attributes:
        agent (str): The agent's ID, as in the machine's agent list.
        enabled (bool): Whether the agent is turned on in Watcher's settings on the machine.
        hooks (None | str): Whether Watcher's hooks are in the agent's configuration and the agent runs them:
            `installed`, `missing`, or `agent_not_found` when they are missing and the agent itself was not found on the
            machine; `untrusted` when they are in place but the agent will not run at least one until the person trusts it
            (Codex asks for this after Watcher's setup installs or changes its hooks), and `turned_off_in_agent` when they
            are in place but the person turned at least one off in the agent's own hook list. Values may be added. Watcher's
            other setup assets (status line, profile command, skill) do not count. Null when the machine could not read it
            or sent a value this server does not know. The machine's hourly agent list carries the same facts as
            `watcher_hooks` (`on` for installed, and also for `untrusted` and `turned_off_in_agent`, which the agent list
            does not tell apart; `off` for missing on an agent turned on; `disabled` for an agent turned off). The two are
            read at different times (compare `received_at` with the agent list's report time), so they can disagree. For
            Claude Code they can also disagree for good: this value counts the agent as found only from files Claude itself
            writes or its command on the path, while the agent list also counts the settings folder, which Watcher's own
            setup creates.
        setup_current (bool | None): Whether Watcher's setup would change nothing for this agent: hooks up to date and
            other assets in place, or for an agent turned off, fully removed. Null when the machine did not report it.
        locked (bool | None): Whether the organization's settings stop a developer from flipping the agent's current
            on/off choice: `permission: locked` on the agent's setting, set there or inherited, or `additions_allowed` for
            an agent the organization's baseline turns on. An agent turned off and locked was turned off by those settings.
            An agent off under `additions_allowed` is not locked, because a developer may turn it on. The machine reports
            this from its own copy of the organization's settings. Null when the machine did not report it; an agent turned
            off with `locked` null is treated like one a developer turned off.
        since (datetime.datetime | None): When the machine first saw the agent's current state: for an agent turned off,
            when it was first seen off; otherwise when the current `enabled` and `hooks` values were first seen together.
            Null when the machine did not report it.
        since_first_check (bool): The state may be older than `since`: it was already in place when the machine first
            checked, when it checked after a stretch without checks, or when it next read the agent's hooks after failing
            to.
        hooks_untrusted_sessions_since (int | None | Unset): With hooks `untrusted`: how many of the agent's session
            files on the machine changed since it stopped running Watcher's hooks (a session can have more than one), over
            the stretch the machine estimates they have been untrusted, which can begin before `since`: from the last change
            to the agent's hooks file before the machine first saw them untrusted, but never from before its last look at
            another hooks state. Zero means no session file of the agent changed in that time (runs that keep no session
            file are never counted). Null for other hooks values, when the machine could not count them completely, or from
            a client too old to count them.
    """

    agent: str
    enabled: bool
    hooks: None | str
    setup_current: bool | None
    locked: bool | None
    since: datetime.datetime | None
    since_first_check: bool
    hooks_untrusted_sessions_since: int | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        agent = self.agent

        enabled = self.enabled

        hooks: None | str
        hooks = self.hooks

        setup_current: bool | None
        setup_current = self.setup_current

        locked: bool | None
        locked = self.locked

        since: None | str
        if isinstance(self.since, datetime.datetime):
            since = self.since.isoformat()
        else:
            since = self.since

        since_first_check = self.since_first_check

        hooks_untrusted_sessions_since: int | None | Unset
        if isinstance(self.hooks_untrusted_sessions_since, Unset):
            hooks_untrusted_sessions_since = UNSET
        else:
            hooks_untrusted_sessions_since = self.hooks_untrusted_sessions_since

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "agent": agent,
                "enabled": enabled,
                "hooks": hooks,
                "setup_current": setup_current,
                "locked": locked,
                "since": since,
                "since_first_check": since_first_check,
            }
        )
        if hooks_untrusted_sessions_since is not UNSET:
            field_dict["hooks_untrusted_sessions_since"] = (
                hooks_untrusted_sessions_since
            )

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        d = dict(src_dict)
        agent = d.pop("agent")

        enabled = d.pop("enabled")

        def _parse_hooks(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        hooks = _parse_hooks(d.pop("hooks"))

        def _parse_setup_current(data: object) -> bool | None:
            if data is None:
                return data
            return cast(bool | None, data)

        setup_current = _parse_setup_current(d.pop("setup_current"))

        def _parse_locked(data: object) -> bool | None:
            if data is None:
                return data
            return cast(bool | None, data)

        locked = _parse_locked(d.pop("locked"))

        def _parse_since(data: object) -> datetime.datetime | None:
            if data is None:
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                since_type_0 = datetime.datetime.fromisoformat(data)

                return since_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None, data)

        since = _parse_since(d.pop("since"))

        since_first_check = d.pop("since_first_check")

        def _parse_hooks_untrusted_sessions_since(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        hooks_untrusted_sessions_since = _parse_hooks_untrusted_sessions_since(
            d.pop("hooks_untrusted_sessions_since", UNSET)
        )

        agent_inventory_health_agent = cls(
            agent=agent,
            enabled=enabled,
            hooks=hooks,
            setup_current=setup_current,
            locked=locked,
            since=since,
            since_first_check=since_first_check,
            hooks_untrusted_sessions_since=hooks_untrusted_sessions_since,
        )

        agent_inventory_health_agent.additional_properties = d
        return agent_inventory_health_agent

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
