from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Self, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="AgentInventoryMissedCallsByReason")


@_attrs_define
class AgentInventoryMissedCallsByReason:
    """Calls in the window by why Watcher did not grade them: `signed_out`, `auth_rejected`,
    `credential_helper_unavailable`, `watcher_offline`, `grading_breaker_hold` (review paused after repeated timeouts),
    `transcript_unavailable`, `empty_transcript`, `hook_error`, `watcher_ignore` (a `.watcher-ignore` file covered the
    session) or `unknown`. Reasons with no calls are absent.

    """

    additional_properties: dict[str, int] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        d = dict(src_dict)
        agent_inventory_missed_calls_by_reason = cls()

        agent_inventory_missed_calls_by_reason.additional_properties = d
        return agent_inventory_missed_calls_by_reason

    @property
    def additional_keys(self) -> list[str]:
        return list(self.additional_properties.keys())

    def __getitem__(self, key: str) -> int:
        return self.additional_properties[key]

    def __setitem__(self, key: str, value: int) -> None:
        self.additional_properties[key] = value

    def __delitem__(self, key: str) -> None:
        del self.additional_properties[key]

    def __contains__(self, key: str) -> bool:
        return key in self.additional_properties
