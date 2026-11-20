from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import Any, Self, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="EndpointHealthAgent")


@_attrs_define
class EndpointHealthAgent:
    """One coding agent Watcher has hooks for: whether it is turned on in Watcher and how its hooks stand.

    Attributes:
        agent (str): The agent's inventory ID, such as `claude_code`.
        enabled (bool): Whether the agent is turned on in Watcher's settings on the machine.
        hooks (None | str | Unset): `installed`, `missing`, `agent_not_found`, `untrusted` (in place, but the agent will
            not run them until the person trusts them) or `turned_off_in_agent` (in place, but turned off in the agent's own
            hook list); null when the check failed.
        setup_current (bool | None | Unset): Whether running Watcher's setup would change nothing for this agent: its
            hooks are up to date and its other setup assets are in place (or, for an agent turned off, fully removed); null
            when the client could not tell.
        locked (bool | None | Unset): Whether the organization's settings stop a developer from flipping the agent's
            current on/off choice: `permission: locked` on `agents.enabled.<name>`, set there or inherited from
            `agents.enabled`, `agents` or the document root; or `additions_allowed` with the agent on because the
            organization's baseline turns it on. An agent off under `additions_allowed` is not locked, because a developer
            may turn it on. This is the rule `watcher agents enable` and `disable` refuse by. Null when the client could not
            read it.
        since (datetime.datetime | None | Unset): When the client first saw the agent's current state: for an agent
            turned off, when it was first seen off, whatever its hooks did since; otherwise when the current `enabled` and
            `hooks` values were first seen together. Null when the client could not keep track.
        since_first_check (bool | Unset): The state may be older than `since`: it was already in place when the client
            first checked, when it checked after a stretch without checks, or when it next read the agent's hooks after
            failing to. Default: False.
    """

    agent: str
    enabled: bool
    hooks: None | str | Unset = UNSET
    setup_current: bool | None | Unset = UNSET
    locked: bool | None | Unset = UNSET
    since: datetime.datetime | None | Unset = UNSET
    since_first_check: bool | Unset = False
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        agent = self.agent

        enabled = self.enabled

        hooks: None | str | Unset
        if isinstance(self.hooks, Unset):
            hooks = UNSET
        else:
            hooks = self.hooks

        setup_current: bool | None | Unset
        if isinstance(self.setup_current, Unset):
            setup_current = UNSET
        else:
            setup_current = self.setup_current

        locked: bool | None | Unset
        if isinstance(self.locked, Unset):
            locked = UNSET
        else:
            locked = self.locked

        since: None | str | Unset
        if isinstance(self.since, Unset):
            since = UNSET
        elif isinstance(self.since, datetime.datetime):
            since = self.since.isoformat()
        else:
            since = self.since

        since_first_check = self.since_first_check

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "agent": agent,
                "enabled": enabled,
            }
        )
        if hooks is not UNSET:
            field_dict["hooks"] = hooks
        if setup_current is not UNSET:
            field_dict["setup_current"] = setup_current
        if locked is not UNSET:
            field_dict["locked"] = locked
        if since is not UNSET:
            field_dict["since"] = since
        if since_first_check is not UNSET:
            field_dict["since_first_check"] = since_first_check

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        d = dict(src_dict)
        agent = d.pop("agent")

        enabled = d.pop("enabled")

        def _parse_hooks(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        hooks = _parse_hooks(d.pop("hooks", UNSET))

        def _parse_setup_current(data: object) -> bool | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(bool | None | Unset, data)

        setup_current = _parse_setup_current(d.pop("setup_current", UNSET))

        def _parse_locked(data: object) -> bool | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(bool | None | Unset, data)

        locked = _parse_locked(d.pop("locked", UNSET))

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

        since_first_check = d.pop("since_first_check", UNSET)

        endpoint_health_agent = cls(
            agent=agent,
            enabled=enabled,
            hooks=hooks,
            setup_current=setup_current,
            locked=locked,
            since=since,
            since_first_check=since_first_check,
        )

        endpoint_health_agent.additional_properties = d
        return endpoint_health_agent

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
