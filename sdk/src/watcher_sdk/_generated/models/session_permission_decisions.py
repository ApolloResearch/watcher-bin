from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="SessionPermissionDecisions")


@_attrs_define
class SessionPermissionDecisions:
    """Per-session counts of notable Watcher permission decisions.

    Each field counts the tool-call decisions in the session that classify into
    the corresponding notable category (see ``NotableDecisionCategory``). The
    classification mirrors the Analyzer ``classifyToolDecision`` helper so the
    session list and the transcript detail view agree on what counts as, e.g., a
    Watcher (automated) denial. Fields are zero when no such decision occurred.

        Attributes:
            human_denied (int | Unset):  Default: 0.
            auto_denied (int | Unset):  Default: 0.
            human_allowed (int | Unset):  Default: 0.
            would_denied (int | Unset):  Default: 0.
            would_escalated (int | Unset):  Default: 0.
    """

    human_denied: int | Unset = 0
    auto_denied: int | Unset = 0
    human_allowed: int | Unset = 0
    would_denied: int | Unset = 0
    would_escalated: int | Unset = 0
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        human_denied = self.human_denied

        auto_denied = self.auto_denied

        human_allowed = self.human_allowed

        would_denied = self.would_denied

        would_escalated = self.would_escalated

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if human_denied is not UNSET:
            field_dict["human_denied"] = human_denied
        if auto_denied is not UNSET:
            field_dict["auto_denied"] = auto_denied
        if human_allowed is not UNSET:
            field_dict["human_allowed"] = human_allowed
        if would_denied is not UNSET:
            field_dict["would_denied"] = would_denied
        if would_escalated is not UNSET:
            field_dict["would_escalated"] = would_escalated

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        human_denied = d.pop("human_denied", UNSET)

        auto_denied = d.pop("auto_denied", UNSET)

        human_allowed = d.pop("human_allowed", UNSET)

        would_denied = d.pop("would_denied", UNSET)

        would_escalated = d.pop("would_escalated", UNSET)

        session_permission_decisions = cls(
            human_denied=human_denied,
            auto_denied=auto_denied,
            human_allowed=human_allowed,
            would_denied=would_denied,
            would_escalated=would_escalated,
        )

        session_permission_decisions.additional_properties = d
        return session_permission_decisions

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
