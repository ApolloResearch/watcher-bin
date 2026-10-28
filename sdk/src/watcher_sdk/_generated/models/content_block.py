from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Self, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.content_block_content_type_1_item import ContentBlockContentType1Item
    from ..models.content_block_input_type_0 import ContentBlockInputType0


T = TypeVar("T", bound="ContentBlock")


@_attrs_define
class ContentBlock:
    """A content block from a Claude API message.

    Accepts extra fields (e.g. 'signature' on thinking blocks) without failing.

        Attributes:
            type_ (str):
            text (None | str | Unset):
            thinking (None | str | Unset):
            signature (None | str | Unset):
            id (None | str | Unset):
            name (None | str | Unset):
            input_ (ContentBlockInputType0 | None | Unset):
            tool_use_id (None | str | Unset):
            content (list[ContentBlockContentType1Item] | None | str | Unset):
    """

    type_: str
    text: None | str | Unset = UNSET
    thinking: None | str | Unset = UNSET
    signature: None | str | Unset = UNSET
    id: None | str | Unset = UNSET
    name: None | str | Unset = UNSET
    input_: ContentBlockInputType0 | None | Unset = UNSET
    tool_use_id: None | str | Unset = UNSET
    content: list[ContentBlockContentType1Item] | None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.content_block_input_type_0 import ContentBlockInputType0

        type_ = self.type_

        text: None | str | Unset
        if isinstance(self.text, Unset):
            text = UNSET
        else:
            text = self.text

        thinking: None | str | Unset
        if isinstance(self.thinking, Unset):
            thinking = UNSET
        else:
            thinking = self.thinking

        signature: None | str | Unset
        if isinstance(self.signature, Unset):
            signature = UNSET
        else:
            signature = self.signature

        id: None | str | Unset
        if isinstance(self.id, Unset):
            id = UNSET
        else:
            id = self.id

        name: None | str | Unset
        if isinstance(self.name, Unset):
            name = UNSET
        else:
            name = self.name

        input_: dict[str, Any] | None | Unset
        if isinstance(self.input_, Unset):
            input_ = UNSET
        elif isinstance(self.input_, ContentBlockInputType0):
            input_ = self.input_.to_dict()
        else:
            input_ = self.input_

        tool_use_id: None | str | Unset
        if isinstance(self.tool_use_id, Unset):
            tool_use_id = UNSET
        else:
            tool_use_id = self.tool_use_id

        content: list[dict[str, Any]] | None | str | Unset
        if isinstance(self.content, Unset):
            content = UNSET
        elif isinstance(self.content, list):
            content = []
            for content_type_1_item_data in self.content:
                content_type_1_item = content_type_1_item_data.to_dict()
                content.append(content_type_1_item)

        else:
            content = self.content

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "type": type_,
            }
        )
        if text is not UNSET:
            field_dict["text"] = text
        if thinking is not UNSET:
            field_dict["thinking"] = thinking
        if signature is not UNSET:
            field_dict["signature"] = signature
        if id is not UNSET:
            field_dict["id"] = id
        if name is not UNSET:
            field_dict["name"] = name
        if input_ is not UNSET:
            field_dict["input"] = input_
        if tool_use_id is not UNSET:
            field_dict["tool_use_id"] = tool_use_id
        if content is not UNSET:
            field_dict["content"] = content

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        from ..models.content_block_content_type_1_item import (
            ContentBlockContentType1Item,
        )
        from ..models.content_block_input_type_0 import ContentBlockInputType0

        d = dict(src_dict)
        type_ = d.pop("type")

        def _parse_text(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        text = _parse_text(d.pop("text", UNSET))

        def _parse_thinking(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        thinking = _parse_thinking(d.pop("thinking", UNSET))

        def _parse_signature(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        signature = _parse_signature(d.pop("signature", UNSET))

        def _parse_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        id = _parse_id(d.pop("id", UNSET))

        def _parse_name(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        name = _parse_name(d.pop("name", UNSET))

        def _parse_input_(data: object) -> ContentBlockInputType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                input_type_0 = ContentBlockInputType0.from_dict(data)

                return input_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(ContentBlockInputType0 | None | Unset, data)

        input_ = _parse_input_(d.pop("input", UNSET))

        def _parse_tool_use_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        tool_use_id = _parse_tool_use_id(d.pop("tool_use_id", UNSET))

        def _parse_content(
            data: object,
        ) -> list[ContentBlockContentType1Item] | None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                content_type_1 = []
                _content_type_1 = data
                for content_type_1_item_data in _content_type_1:
                    content_type_1_item = ContentBlockContentType1Item.from_dict(
                        content_type_1_item_data
                    )

                    content_type_1.append(content_type_1_item)

                return content_type_1
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(list[ContentBlockContentType1Item] | None | str | Unset, data)

        content = _parse_content(d.pop("content", UNSET))

        content_block = cls(
            type_=type_,
            text=text,
            thinking=thinking,
            signature=signature,
            id=id,
            name=name,
            input_=input_,
            tool_use_id=tool_use_id,
            content=content,
        )

        content_block.additional_properties = d
        return content_block

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
