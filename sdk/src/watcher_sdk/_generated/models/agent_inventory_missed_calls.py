from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Self, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.agent_inventory_missed_calls_by_reason import (
        AgentInventoryMissedCallsByReason,
    )


T = TypeVar("T", bound="AgentInventoryMissedCalls")


@_attrs_define
class AgentInventoryMissedCalls:
    """Tool calls the machine's Watcher client observed but did not grade in the last 7 days, by reason.

    Counted from the metadata-only tool-call records the client sent naming this installation: counts only, never
    tool names, IDs or content. A call graded after all (its record was replaced by an evaluation) is not counted.

        Attributes:
            since (datetime.datetime): The start of the window: 7 days before the read.
            total (int): Calls recorded in the window; 0 when there were none.
            by_reason (AgentInventoryMissedCallsByReason): Calls in the window by why Watcher did not grade them:
                `signed_out`, `auth_rejected`, `credential_helper_unavailable`, `watcher_offline`, `grading_breaker_hold`
                (review paused after repeated timeouts), `transcript_unavailable`, `empty_transcript`, `hook_error`,
                `watcher_ignore` (a `.watcher-ignore` file covered the session) or `unknown`. Reasons with no calls are absent.
    """

    since: datetime.datetime
    total: int
    by_reason: AgentInventoryMissedCallsByReason
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        since = self.since.isoformat()

        total = self.total

        by_reason = self.by_reason.to_dict()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "since": since,
                "total": total,
                "by_reason": by_reason,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        from ..models.agent_inventory_missed_calls_by_reason import (
            AgentInventoryMissedCallsByReason,
        )

        d = dict(src_dict)
        since = datetime.datetime.fromisoformat(d.pop("since"))

        total = d.pop("total")

        by_reason = AgentInventoryMissedCallsByReason.from_dict(d.pop("by_reason"))

        agent_inventory_missed_calls = cls(
            since=since,
            total=total,
            by_reason=by_reason,
        )

        agent_inventory_missed_calls.additional_properties = d
        return agent_inventory_missed_calls

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
