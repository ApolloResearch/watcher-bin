from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Self, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="TrajectoryDetailResponseMetadata")


@_attrs_define
class TrajectoryDetailResponseMetadata:
    """The stored metadata of this transcript's own last stored message only, not combined across messages as the session's
    metadata is. For Claude Code, 'claude_code_entrypoint' and 'claude_code_entry_version' come from the transcript
    entry that message came from. For Codex ('originator', 'cli_version') and GitHub Copilot CLI ('cli_version') they
    are the session record's values copied onto every message of the upload, so they do not show which release wrote
    that message. The upload's own metadata, such as 'hostname', is also included. Values can differ from the session's
    'entrypoint' and 'agent_version' after a resume or an upgrade.

    """

    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        d = dict(src_dict)
        trajectory_detail_response_metadata = cls()

        trajectory_detail_response_metadata.additional_properties = d
        return trajectory_detail_response_metadata

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
