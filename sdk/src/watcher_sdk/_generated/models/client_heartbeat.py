from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import Any, Self, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="ClientHeartbeat")


@_attrs_define
class ClientHeartbeat:
    """The client's heartbeat, sent every 15 minutes whatever the organization's agent inventory setting.

    The client also sends one at once when something changes whether it can report: the machine going to sleep
    or waking, the client stopping, or someone signing it out (``event``). Unknown fields are ignored.

        Attributes:
            observed_at (datetime.datetime): When the client built this heartbeat, by its own clock.
            client_version (str): The Watcher client's version.
            event (None | str | Unset): Why this heartbeat was sent outside the schedule: `going_to_sleep`, `woke`,
                `stopping`, `stopped_by_user` or `signing_out` (see `ClientEventValue`); null for a scheduled heartbeat. An open
                string: a server ignores an event it does not know.
            asleep_since (datetime.datetime | None | Unset): With `woke`: when the machine went to sleep, by the client's
                clock (the last time the client saw itself running before the sleep). Null otherwise.
            process_started_at (datetime.datetime | None | Unset): When the client's background process started, by its
                clock. Null when unknown.
            system_booted_at (datetime.datetime | None | Unset): When the machine last booted, by its clock. Null when the
                client could not read it.
    """

    observed_at: datetime.datetime
    client_version: str
    event: None | str | Unset = UNSET
    asleep_since: datetime.datetime | None | Unset = UNSET
    process_started_at: datetime.datetime | None | Unset = UNSET
    system_booted_at: datetime.datetime | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        observed_at = self.observed_at.isoformat()

        client_version = self.client_version

        event: None | str | Unset
        if isinstance(self.event, Unset):
            event = UNSET
        else:
            event = self.event

        asleep_since: None | str | Unset
        if isinstance(self.asleep_since, Unset):
            asleep_since = UNSET
        elif isinstance(self.asleep_since, datetime.datetime):
            asleep_since = self.asleep_since.isoformat()
        else:
            asleep_since = self.asleep_since

        process_started_at: None | str | Unset
        if isinstance(self.process_started_at, Unset):
            process_started_at = UNSET
        elif isinstance(self.process_started_at, datetime.datetime):
            process_started_at = self.process_started_at.isoformat()
        else:
            process_started_at = self.process_started_at

        system_booted_at: None | str | Unset
        if isinstance(self.system_booted_at, Unset):
            system_booted_at = UNSET
        elif isinstance(self.system_booted_at, datetime.datetime):
            system_booted_at = self.system_booted_at.isoformat()
        else:
            system_booted_at = self.system_booted_at

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "observed_at": observed_at,
                "client_version": client_version,
            }
        )
        if event is not UNSET:
            field_dict["event"] = event
        if asleep_since is not UNSET:
            field_dict["asleep_since"] = asleep_since
        if process_started_at is not UNSET:
            field_dict["process_started_at"] = process_started_at
        if system_booted_at is not UNSET:
            field_dict["system_booted_at"] = system_booted_at

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        d = dict(src_dict)
        observed_at = datetime.datetime.fromisoformat(d.pop("observed_at"))

        client_version = d.pop("client_version")

        def _parse_event(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        event = _parse_event(d.pop("event", UNSET))

        def _parse_asleep_since(data: object) -> datetime.datetime | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                asleep_since_type_0 = datetime.datetime.fromisoformat(data)

                return asleep_since_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None | Unset, data)

        asleep_since = _parse_asleep_since(d.pop("asleep_since", UNSET))

        def _parse_process_started_at(data: object) -> datetime.datetime | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                process_started_at_type_0 = datetime.datetime.fromisoformat(data)

                return process_started_at_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None | Unset, data)

        process_started_at = _parse_process_started_at(
            d.pop("process_started_at", UNSET)
        )

        def _parse_system_booted_at(data: object) -> datetime.datetime | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                system_booted_at_type_0 = datetime.datetime.fromisoformat(data)

                return system_booted_at_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None | Unset, data)

        system_booted_at = _parse_system_booted_at(d.pop("system_booted_at", UNSET))

        client_heartbeat = cls(
            observed_at=observed_at,
            client_version=client_version,
            event=event,
            asleep_since=asleep_since,
            process_started_at=process_started_at,
            system_booted_at=system_booted_at,
        )

        client_heartbeat.additional_properties = d
        return client_heartbeat

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
