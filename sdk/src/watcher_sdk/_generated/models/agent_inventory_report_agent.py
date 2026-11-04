from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import Any, Self, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="AgentInventoryReportAgent")


@_attrs_define
class AgentInventoryReportAgent:
    """One agent found on the machine.

    Attributes:
        id (str): The agent's inventory ID.
        surfaces (list[str] | Unset): Where the agent is installed: `cli`, `ide`, `ide_extension`, `desktop_app` or
            `sdk`.
        version (None | str | Unset): The newest installed version, if known.
        last_used_on (datetime.date | None | Unset): The UTC date the agent was last used, if known.
        recent_sessions (int | None | Unset): Session files modified in the last 7 days, or null when they cannot be
            counted.
        watcher_hooks (str | Unset): Whether Watcher's hooks are set up for this agent: `on`; `off` when the agent is
            turned on in Watcher but its hooks are not installed; `disabled` when the agent is turned off in Watcher; or
            `not_applicable` when Watcher has no hooks for it. Default: 'not_applicable'.
        settings_folder_only (bool | Unset): True when the only trace of the agent is its settings folder: no installed
            program, extension or app, and no session files. Someone set the agent up on this machine once; it may have been
            removed. Default: False.
    """

    id: str
    surfaces: list[str] | Unset = UNSET
    version: None | str | Unset = UNSET
    last_used_on: datetime.date | None | Unset = UNSET
    recent_sessions: int | None | Unset = UNSET
    watcher_hooks: str | Unset = "not_applicable"
    settings_folder_only: bool | Unset = False
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        id = self.id

        surfaces: list[str] | Unset = UNSET
        if not isinstance(self.surfaces, Unset):
            surfaces = self.surfaces

        version: None | str | Unset
        if isinstance(self.version, Unset):
            version = UNSET
        else:
            version = self.version

        last_used_on: None | str | Unset
        if isinstance(self.last_used_on, Unset):
            last_used_on = UNSET
        elif isinstance(self.last_used_on, datetime.date):
            last_used_on = self.last_used_on.isoformat()
        else:
            last_used_on = self.last_used_on

        recent_sessions: int | None | Unset
        if isinstance(self.recent_sessions, Unset):
            recent_sessions = UNSET
        else:
            recent_sessions = self.recent_sessions

        watcher_hooks = self.watcher_hooks

        settings_folder_only = self.settings_folder_only

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "id": id,
            }
        )
        if surfaces is not UNSET:
            field_dict["surfaces"] = surfaces
        if version is not UNSET:
            field_dict["version"] = version
        if last_used_on is not UNSET:
            field_dict["last_used_on"] = last_used_on
        if recent_sessions is not UNSET:
            field_dict["recent_sessions"] = recent_sessions
        if watcher_hooks is not UNSET:
            field_dict["watcher_hooks"] = watcher_hooks
        if settings_folder_only is not UNSET:
            field_dict["settings_folder_only"] = settings_folder_only

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        d = dict(src_dict)
        id = d.pop("id")

        surfaces = cast(list[str], d.pop("surfaces", UNSET))

        def _parse_version(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        version = _parse_version(d.pop("version", UNSET))

        def _parse_last_used_on(data: object) -> datetime.date | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                last_used_on_type_0 = datetime.date.fromisoformat(data)

                return last_used_on_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.date | None | Unset, data)

        last_used_on = _parse_last_used_on(d.pop("last_used_on", UNSET))

        def _parse_recent_sessions(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        recent_sessions = _parse_recent_sessions(d.pop("recent_sessions", UNSET))

        watcher_hooks = d.pop("watcher_hooks", UNSET)

        settings_folder_only = d.pop("settings_folder_only", UNSET)

        agent_inventory_report_agent = cls(
            id=id,
            surfaces=surfaces,
            version=version,
            last_used_on=last_used_on,
            recent_sessions=recent_sessions,
            watcher_hooks=watcher_hooks,
            settings_folder_only=settings_folder_only,
        )

        agent_inventory_report_agent.additional_properties = d
        return agent_inventory_report_agent

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
