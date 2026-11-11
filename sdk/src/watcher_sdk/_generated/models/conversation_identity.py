from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Self, TypeVar

from attrs import define as _attrs_define

from ..models.conversation_identity_namespace import ConversationIdentityNamespace

T = TypeVar("T", bound="ConversationIdentity")


@_attrs_define
class ConversationIdentity:
    """One authoritative session-matching identity, without additional aliases.

    Native Codex IDs and Claude root IDs are normalized UUIDs. Claude children use
    the transcript uploader's ``subagent:[root_uuid, agent_id]`` encoding. Custom
    IDs belong to ``other`` and keep any integration namespace supplied by their
    adapter. The larger wire limit accommodates JSON-escaped child identifiers;
    individual native identifiers remain bounded at 1,024 characters.

        Attributes:
            namespace (ConversationIdentityNamespace):
            id (str):
    """

    namespace: ConversationIdentityNamespace
    id: str

    def to_dict(self) -> dict[str, Any]:
        namespace = self.namespace.value

        id = self.id

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "namespace": namespace,
                "id": id,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        d = dict(src_dict)
        namespace = ConversationIdentityNamespace(d.pop("namespace"))

        id = d.pop("id")

        conversation_identity = cls(
            namespace=namespace,
            id=id,
        )

        return conversation_identity
