from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.message_detail_response_message import MessageDetailResponseMessage


T = TypeVar("T", bound="MessageDetailResponse")


@_attrs_define
class MessageDetailResponse:
    """One full-content message from GET /sessions/{sid}/messages/{message_ref}.

    Backs per-elision expansion in the Analyzer: the truncated trajectory view marks
    what it elided, and this response carries the single message's stored content so
    the client never refetches the whole trajectory to expand one item. The message
    uses the same wire shape as trajectory-response messages.

        Attributes:
            message (MessageDetailResponseMessage):
    """

    message: MessageDetailResponseMessage
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        message = self.message.to_dict()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "message": message,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.message_detail_response_message import (
            MessageDetailResponseMessage,
        )

        d = dict(src_dict)
        message = MessageDetailResponseMessage.from_dict(d.pop("message"))

        message_detail_response = cls(
            message=message,
        )

        message_detail_response.additional_properties = d
        return message_detail_response

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
