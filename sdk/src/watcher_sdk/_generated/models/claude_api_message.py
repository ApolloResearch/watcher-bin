from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Self, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.claude_api_message_usage_type_0 import ClaudeAPIMessageUsageType0
    from ..models.content_block import ContentBlock


T = TypeVar("T", bound="ClaudeAPIMessage")


@_attrs_define
class ClaudeAPIMessage:
    """A message from the Claude API. Accepts extra fields like 'type', 'stop_reason'.

    Attributes:
        role (str):
        content (list[ContentBlock] | str):
        model (None | str | Unset):
        id (None | str | Unset):
        usage (ClaudeAPIMessageUsageType0 | None | Unset):
        stop_reason (None | str | Unset):
    """

    role: str
    content: list[ContentBlock] | str
    model: None | str | Unset = UNSET
    id: None | str | Unset = UNSET
    usage: ClaudeAPIMessageUsageType0 | None | Unset = UNSET
    stop_reason: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.claude_api_message_usage_type_0 import ClaudeAPIMessageUsageType0

        role = self.role

        content: list[dict[str, Any]] | str
        if isinstance(self.content, list):
            content = []
            for content_type_1_item_data in self.content:
                content_type_1_item = content_type_1_item_data.to_dict()
                content.append(content_type_1_item)

        else:
            content = self.content

        model: None | str | Unset
        if isinstance(self.model, Unset):
            model = UNSET
        else:
            model = self.model

        id: None | str | Unset
        if isinstance(self.id, Unset):
            id = UNSET
        else:
            id = self.id

        usage: dict[str, Any] | None | Unset
        if isinstance(self.usage, Unset):
            usage = UNSET
        elif isinstance(self.usage, ClaudeAPIMessageUsageType0):
            usage = self.usage.to_dict()
        else:
            usage = self.usage

        stop_reason: None | str | Unset
        if isinstance(self.stop_reason, Unset):
            stop_reason = UNSET
        else:
            stop_reason = self.stop_reason

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "role": role,
                "content": content,
            }
        )
        if model is not UNSET:
            field_dict["model"] = model
        if id is not UNSET:
            field_dict["id"] = id
        if usage is not UNSET:
            field_dict["usage"] = usage
        if stop_reason is not UNSET:
            field_dict["stop_reason"] = stop_reason

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        from ..models.claude_api_message_usage_type_0 import ClaudeAPIMessageUsageType0
        from ..models.content_block import ContentBlock

        d = dict(src_dict)
        role = d.pop("role")

        def _parse_content(data: object) -> list[ContentBlock] | str:
            try:
                if not isinstance(data, list):
                    raise TypeError()
                content_type_1 = []
                _content_type_1 = data
                for content_type_1_item_data in _content_type_1:
                    content_type_1_item = ContentBlock.from_dict(
                        content_type_1_item_data
                    )

                    content_type_1.append(content_type_1_item)

                return content_type_1
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(list[ContentBlock] | str, data)

        content = _parse_content(d.pop("content"))

        def _parse_model(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        model = _parse_model(d.pop("model", UNSET))

        def _parse_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        id = _parse_id(d.pop("id", UNSET))

        def _parse_usage(data: object) -> ClaudeAPIMessageUsageType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                usage_type_0 = ClaudeAPIMessageUsageType0.from_dict(data)

                return usage_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(ClaudeAPIMessageUsageType0 | None | Unset, data)

        usage = _parse_usage(d.pop("usage", UNSET))

        def _parse_stop_reason(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        stop_reason = _parse_stop_reason(d.pop("stop_reason", UNSET))

        claude_api_message = cls(
            role=role,
            content=content,
            model=model,
            id=id,
            usage=usage,
            stop_reason=stop_reason,
        )

        claude_api_message.additional_properties = d
        return claude_api_message

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
