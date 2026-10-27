from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from typing_extensions import Self

T = TypeVar("T", bound="ClaudeCodeAgentIdentity")


@_attrs_define
class ClaudeCodeAgentIdentity:
    """Identify one child independently of its root conversation and siblings.

    Supply this on every full and incremental child upload. The root conversation
    is Claude Code's native session ID; agent_id identifies the child transcript,
    including when the child's immediate parent is another child.

        Attributes:
            root_session_id (str):
            agent_id (str):
    """

    root_session_id: str
    agent_id: str

    def to_dict(self) -> dict[str, Any]:
        root_session_id = self.root_session_id

        agent_id = self.agent_id

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "root_session_id": root_session_id,
                "agent_id": agent_id,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        d = dict(src_dict)
        root_session_id = d.pop("root_session_id")

        agent_id = d.pop("agent_id")

        claude_code_agent_identity = cls(
            root_session_id=root_session_id,
            agent_id=agent_id,
        )

        return claude_code_agent_identity
