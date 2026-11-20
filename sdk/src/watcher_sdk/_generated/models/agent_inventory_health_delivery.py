from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import Any, Self, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="AgentInventoryHealthDelivery")


@_attrs_define
class AgentInventoryHealthDelivery:
    """What the machine was still waiting to upload. A null count means the machine could not read it.

    Attributes:
        decisions_waiting (int | None): Tool-call decisions waiting to upload.
        oldest_decision_at (datetime.datetime | None): When the oldest decision still waiting was made; null when none
            is waiting.
        decisions_gave_up (int | None): Decisions from the last 7 days the machine stopped retrying.
        transcripts_waiting (int | None): Session transcripts waiting to upload that still have retries left.
        call_records_waiting (int | None | Unset): Records of tool calls Watcher observed but did not grade, captured on
            the machine and not yet sent; null when the machine could not read them or its client does not report them.
    """

    decisions_waiting: int | None
    oldest_decision_at: datetime.datetime | None
    decisions_gave_up: int | None
    transcripts_waiting: int | None
    call_records_waiting: int | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        decisions_waiting: int | None
        decisions_waiting = self.decisions_waiting

        oldest_decision_at: None | str
        if isinstance(self.oldest_decision_at, datetime.datetime):
            oldest_decision_at = self.oldest_decision_at.isoformat()
        else:
            oldest_decision_at = self.oldest_decision_at

        decisions_gave_up: int | None
        decisions_gave_up = self.decisions_gave_up

        transcripts_waiting: int | None
        transcripts_waiting = self.transcripts_waiting

        call_records_waiting: int | None | Unset
        if isinstance(self.call_records_waiting, Unset):
            call_records_waiting = UNSET
        else:
            call_records_waiting = self.call_records_waiting

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "decisions_waiting": decisions_waiting,
                "oldest_decision_at": oldest_decision_at,
                "decisions_gave_up": decisions_gave_up,
                "transcripts_waiting": transcripts_waiting,
            }
        )
        if call_records_waiting is not UNSET:
            field_dict["call_records_waiting"] = call_records_waiting

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        d = dict(src_dict)

        def _parse_decisions_waiting(data: object) -> int | None:
            if data is None:
                return data
            return cast(int | None, data)

        decisions_waiting = _parse_decisions_waiting(d.pop("decisions_waiting"))

        def _parse_oldest_decision_at(data: object) -> datetime.datetime | None:
            if data is None:
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                oldest_decision_at_type_0 = datetime.datetime.fromisoformat(data)

                return oldest_decision_at_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None, data)

        oldest_decision_at = _parse_oldest_decision_at(d.pop("oldest_decision_at"))

        def _parse_decisions_gave_up(data: object) -> int | None:
            if data is None:
                return data
            return cast(int | None, data)

        decisions_gave_up = _parse_decisions_gave_up(d.pop("decisions_gave_up"))

        def _parse_transcripts_waiting(data: object) -> int | None:
            if data is None:
                return data
            return cast(int | None, data)

        transcripts_waiting = _parse_transcripts_waiting(d.pop("transcripts_waiting"))

        def _parse_call_records_waiting(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        call_records_waiting = _parse_call_records_waiting(
            d.pop("call_records_waiting", UNSET)
        )

        agent_inventory_health_delivery = cls(
            decisions_waiting=decisions_waiting,
            oldest_decision_at=oldest_decision_at,
            decisions_gave_up=decisions_gave_up,
            transcripts_waiting=transcripts_waiting,
            call_records_waiting=call_records_waiting,
        )

        agent_inventory_health_delivery.additional_properties = d
        return agent_inventory_health_delivery

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
