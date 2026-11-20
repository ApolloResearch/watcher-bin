from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import Any, Self, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="EndpointHealthDelivery")


@_attrs_define
class EndpointHealthDelivery:
    """What the machine is still waiting to upload. A null count means the client could not read it.

    Attributes:
        decisions_waiting (int | None | Unset): Tool-call decisions waiting to upload.
        oldest_decision_at (datetime.datetime | None | Unset): When the oldest decision still waiting was made; null
            when none is waiting.
        decisions_gave_up (int | None | Unset): Decisions from the last 7 days the client stopped retrying.
        transcripts_waiting (int | None | Unset): Session transcripts waiting to upload that have retries left.
        call_records_waiting (int | None | Unset): Records of tool calls Watcher observed but did not grade, captured
            and not yet sent.
    """

    decisions_waiting: int | None | Unset = UNSET
    oldest_decision_at: datetime.datetime | None | Unset = UNSET
    decisions_gave_up: int | None | Unset = UNSET
    transcripts_waiting: int | None | Unset = UNSET
    call_records_waiting: int | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        decisions_waiting: int | None | Unset
        if isinstance(self.decisions_waiting, Unset):
            decisions_waiting = UNSET
        else:
            decisions_waiting = self.decisions_waiting

        oldest_decision_at: None | str | Unset
        if isinstance(self.oldest_decision_at, Unset):
            oldest_decision_at = UNSET
        elif isinstance(self.oldest_decision_at, datetime.datetime):
            oldest_decision_at = self.oldest_decision_at.isoformat()
        else:
            oldest_decision_at = self.oldest_decision_at

        decisions_gave_up: int | None | Unset
        if isinstance(self.decisions_gave_up, Unset):
            decisions_gave_up = UNSET
        else:
            decisions_gave_up = self.decisions_gave_up

        transcripts_waiting: int | None | Unset
        if isinstance(self.transcripts_waiting, Unset):
            transcripts_waiting = UNSET
        else:
            transcripts_waiting = self.transcripts_waiting

        call_records_waiting: int | None | Unset
        if isinstance(self.call_records_waiting, Unset):
            call_records_waiting = UNSET
        else:
            call_records_waiting = self.call_records_waiting

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if decisions_waiting is not UNSET:
            field_dict["decisions_waiting"] = decisions_waiting
        if oldest_decision_at is not UNSET:
            field_dict["oldest_decision_at"] = oldest_decision_at
        if decisions_gave_up is not UNSET:
            field_dict["decisions_gave_up"] = decisions_gave_up
        if transcripts_waiting is not UNSET:
            field_dict["transcripts_waiting"] = transcripts_waiting
        if call_records_waiting is not UNSET:
            field_dict["call_records_waiting"] = call_records_waiting

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        d = dict(src_dict)

        def _parse_decisions_waiting(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        decisions_waiting = _parse_decisions_waiting(d.pop("decisions_waiting", UNSET))

        def _parse_oldest_decision_at(data: object) -> datetime.datetime | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                oldest_decision_at_type_0 = datetime.datetime.fromisoformat(data)

                return oldest_decision_at_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None | Unset, data)

        oldest_decision_at = _parse_oldest_decision_at(
            d.pop("oldest_decision_at", UNSET)
        )

        def _parse_decisions_gave_up(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        decisions_gave_up = _parse_decisions_gave_up(d.pop("decisions_gave_up", UNSET))

        def _parse_transcripts_waiting(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        transcripts_waiting = _parse_transcripts_waiting(
            d.pop("transcripts_waiting", UNSET)
        )

        def _parse_call_records_waiting(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        call_records_waiting = _parse_call_records_waiting(
            d.pop("call_records_waiting", UNSET)
        )

        endpoint_health_delivery = cls(
            decisions_waiting=decisions_waiting,
            oldest_decision_at=oldest_decision_at,
            decisions_gave_up=decisions_gave_up,
            transcripts_waiting=transcripts_waiting,
            call_records_waiting=call_records_waiting,
        )

        endpoint_health_delivery.additional_properties = d
        return endpoint_health_delivery

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
