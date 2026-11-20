from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Self, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.agent_inventory_activity_event import AgentInventoryActivityEvent


T = TypeVar("T", bound="AgentInventoryActivityResponse")


@_attrs_define
class AgentInventoryActivityResponse:
    """Changes on machines running the Watcher client over the last 7 days, newest first.

    One machine's feed lists every change in the 7 days. The organization-wide feed lists no silences (the machine
    list's `presence` shows each machine that is offline); it lists the other changes since
    `recent_since` and, from earlier in the 7 days, only the changes whose state still holds. The
    organization-wide feed can be up to 5 minutes old (`generated_at`).

        Attributes:
            generated_at (datetime.datetime): When the server computed this feed. The organization-wide feed is reused for
                up to 5 minutes, so it can be that old and miss changes reported since; one machine's feed is computed for each
                request.
            since (datetime.datetime): The start of the window: 7 days before `generated_at`. An ongoing silence in one
                machine's feed can have an earlier `at`.
            recent_since (datetime.datetime | None): For the organization-wide feed, the start of the window in which every
                change except a silence is listed: 24 hours before `generated_at` (not the summary's 7-day recent window).
                Earlier changes in the 7 days are listed only while their state still holds, only when the machine's reports say
                when they began (not a state the client found already in place, nor a pause with no other mode read in the 7
                days), and only for the problem kinds that can hold (everything but silences, updates and the kinds that end a
                problem). While the organization's own mode is paused, which the server knows only when Watcher distributes its
                settings, machines pausing are left out of both parts; under MDM distribution every machine's pause is listed.
                Null for a single machine, whose feed lists every change since `since`, silences included.
            events (list[AgentInventoryActivityEvent]): The changes, newest `at` first.
            truncated (bool): True when there were more than 2,000 changes, the most one response holds; there is no paging.
                Changes that still hold are kept first, a machine's own states before changes the organization made to every
                machine at once (a mode change other than a pause, an agent locked off by its settings), then the newest.
    """

    generated_at: datetime.datetime
    since: datetime.datetime
    recent_since: datetime.datetime | None
    events: list[AgentInventoryActivityEvent]
    truncated: bool
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        generated_at = self.generated_at.isoformat()

        since = self.since.isoformat()

        recent_since: None | str
        if isinstance(self.recent_since, datetime.datetime):
            recent_since = self.recent_since.isoformat()
        else:
            recent_since = self.recent_since

        events = []
        for events_item_data in self.events:
            events_item = events_item_data.to_dict()
            events.append(events_item)

        truncated = self.truncated

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "generated_at": generated_at,
                "since": since,
                "recent_since": recent_since,
                "events": events,
                "truncated": truncated,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        from ..models.agent_inventory_activity_event import AgentInventoryActivityEvent

        d = dict(src_dict)
        generated_at = datetime.datetime.fromisoformat(d.pop("generated_at"))

        since = datetime.datetime.fromisoformat(d.pop("since"))

        def _parse_recent_since(data: object) -> datetime.datetime | None:
            if data is None:
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                recent_since_type_0 = datetime.datetime.fromisoformat(data)

                return recent_since_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None, data)

        recent_since = _parse_recent_since(d.pop("recent_since"))

        events = []
        _events = d.pop("events")
        for events_item_data in _events:
            events_item = AgentInventoryActivityEvent.from_dict(events_item_data)

            events.append(events_item)

        truncated = d.pop("truncated")

        agent_inventory_activity_response = cls(
            generated_at=generated_at,
            since=since,
            recent_since=recent_since,
            events=events,
            truncated=truncated,
        )

        agent_inventory_activity_response.additional_properties = d
        return agent_inventory_activity_response

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
