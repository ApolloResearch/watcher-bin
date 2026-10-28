from __future__ import annotations

from collections.abc import Mapping
from typing import (
    TYPE_CHECKING,
    Any,
    Literal,
    Self,
    TypeVar,
    cast,
)

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.chat_message_assistant_source_type_0 import (
    ChatMessageAssistantSourceType0,
)
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.chat_message_assistant_metadata_type_0 import (
        ChatMessageAssistantMetadataType0,
    )
    from ..models.content_audio import ContentAudio
    from ..models.content_data import ContentData
    from ..models.content_document import ContentDocument
    from ..models.content_image import ContentImage
    from ..models.content_reasoning import ContentReasoning
    from ..models.content_text import ContentText
    from ..models.content_tool_use import ContentToolUse
    from ..models.content_video import ContentVideo
    from ..models.tool_call import ToolCall


T = TypeVar("T", bound="ChatMessageAssistant")


@_attrs_define
class ChatMessageAssistant:
    """Assistant chat message.

    Attributes:
        content (list[ContentAudio | ContentData | ContentDocument | ContentImage | ContentReasoning | ContentText |
            ContentToolUse | ContentVideo] | str):
        id (None | str | Unset):
        source (ChatMessageAssistantSourceType0 | None | Unset):
        metadata (ChatMessageAssistantMetadataType0 | None | Unset):
        role (Literal['assistant'] | Unset):  Default: 'assistant'.
        tool_calls (list[ToolCall] | None | Unset):
        model (None | str | Unset):
    """

    content: (
        list[
            ContentAudio
            | ContentData
            | ContentDocument
            | ContentImage
            | ContentReasoning
            | ContentText
            | ContentToolUse
            | ContentVideo
        ]
        | str
    )
    id: None | str | Unset = UNSET
    source: ChatMessageAssistantSourceType0 | None | Unset = UNSET
    metadata: ChatMessageAssistantMetadataType0 | None | Unset = UNSET
    role: Literal["assistant"] | Unset = "assistant"
    tool_calls: list[ToolCall] | None | Unset = UNSET
    model: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.chat_message_assistant_metadata_type_0 import (
            ChatMessageAssistantMetadataType0,
        )
        from ..models.content_audio import ContentAudio
        from ..models.content_data import ContentData
        from ..models.content_image import ContentImage
        from ..models.content_reasoning import ContentReasoning
        from ..models.content_text import ContentText
        from ..models.content_tool_use import ContentToolUse
        from ..models.content_video import ContentVideo

        content: list[dict[str, Any]] | str
        if isinstance(self.content, list):
            content = []
            for content_type_1_item_data in self.content:
                content_type_1_item: dict[str, Any]
                if (
                    isinstance(content_type_1_item_data, ContentText)
                    or isinstance(content_type_1_item_data, ContentReasoning)
                    or isinstance(content_type_1_item_data, ContentImage)
                    or isinstance(content_type_1_item_data, ContentAudio)
                    or isinstance(content_type_1_item_data, ContentVideo)
                    or isinstance(content_type_1_item_data, ContentData)
                    or isinstance(content_type_1_item_data, ContentToolUse)
                ):
                    content_type_1_item = content_type_1_item_data.to_dict()
                else:
                    content_type_1_item = content_type_1_item_data.to_dict()

                content.append(content_type_1_item)

        else:
            content = self.content

        id: None | str | Unset
        if isinstance(self.id, Unset):
            id = UNSET
        else:
            id = self.id

        source: None | str | Unset
        if isinstance(self.source, Unset):
            source = UNSET
        elif isinstance(self.source, ChatMessageAssistantSourceType0):
            source = self.source.value
        else:
            source = self.source

        metadata: dict[str, Any] | None | Unset
        if isinstance(self.metadata, Unset):
            metadata = UNSET
        elif isinstance(self.metadata, ChatMessageAssistantMetadataType0):
            metadata = self.metadata.to_dict()
        else:
            metadata = self.metadata

        role = self.role

        tool_calls: list[dict[str, Any]] | None | Unset
        if isinstance(self.tool_calls, Unset):
            tool_calls = UNSET
        elif isinstance(self.tool_calls, list):
            tool_calls = []
            for tool_calls_type_0_item_data in self.tool_calls:
                tool_calls_type_0_item = tool_calls_type_0_item_data.to_dict()
                tool_calls.append(tool_calls_type_0_item)

        else:
            tool_calls = self.tool_calls

        model: None | str | Unset
        if isinstance(self.model, Unset):
            model = UNSET
        else:
            model = self.model

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "content": content,
            }
        )
        if id is not UNSET:
            field_dict["id"] = id
        if source is not UNSET:
            field_dict["source"] = source
        if metadata is not UNSET:
            field_dict["metadata"] = metadata
        if role is not UNSET:
            field_dict["role"] = role
        if tool_calls is not UNSET:
            field_dict["tool_calls"] = tool_calls
        if model is not UNSET:
            field_dict["model"] = model

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        from ..models.chat_message_assistant_metadata_type_0 import (
            ChatMessageAssistantMetadataType0,
        )
        from ..models.content_audio import ContentAudio
        from ..models.content_data import ContentData
        from ..models.content_document import ContentDocument
        from ..models.content_image import ContentImage
        from ..models.content_reasoning import ContentReasoning
        from ..models.content_text import ContentText
        from ..models.content_tool_use import ContentToolUse
        from ..models.content_video import ContentVideo
        from ..models.tool_call import ToolCall

        d = dict(src_dict)

        def _parse_content(
            data: object,
        ) -> (
            list[
                ContentAudio
                | ContentData
                | ContentDocument
                | ContentImage
                | ContentReasoning
                | ContentText
                | ContentToolUse
                | ContentVideo
            ]
            | str
        ):
            try:
                if not isinstance(data, list):
                    raise TypeError()
                content_type_1 = []
                _content_type_1 = data
                for content_type_1_item_data in _content_type_1:

                    def _parse_content_type_1_item(
                        data: object,
                    ) -> (
                        ContentAudio
                        | ContentData
                        | ContentDocument
                        | ContentImage
                        | ContentReasoning
                        | ContentText
                        | ContentToolUse
                        | ContentVideo
                    ):
                        try:
                            if not isinstance(data, dict):
                                raise TypeError()
                            content_type_1_item_type_0 = ContentText.from_dict(data)

                            return content_type_1_item_type_0
                        except (TypeError, ValueError, AttributeError, KeyError):
                            pass
                        try:
                            if not isinstance(data, dict):
                                raise TypeError()
                            content_type_1_item_type_1 = ContentReasoning.from_dict(
                                data
                            )

                            return content_type_1_item_type_1
                        except (TypeError, ValueError, AttributeError, KeyError):
                            pass
                        try:
                            if not isinstance(data, dict):
                                raise TypeError()
                            content_type_1_item_type_2 = ContentImage.from_dict(data)

                            return content_type_1_item_type_2
                        except (TypeError, ValueError, AttributeError, KeyError):
                            pass
                        try:
                            if not isinstance(data, dict):
                                raise TypeError()
                            content_type_1_item_type_3 = ContentAudio.from_dict(data)

                            return content_type_1_item_type_3
                        except (TypeError, ValueError, AttributeError, KeyError):
                            pass
                        try:
                            if not isinstance(data, dict):
                                raise TypeError()
                            content_type_1_item_type_4 = ContentVideo.from_dict(data)

                            return content_type_1_item_type_4
                        except (TypeError, ValueError, AttributeError, KeyError):
                            pass
                        try:
                            if not isinstance(data, dict):
                                raise TypeError()
                            content_type_1_item_type_5 = ContentData.from_dict(data)

                            return content_type_1_item_type_5
                        except (TypeError, ValueError, AttributeError, KeyError):
                            pass
                        try:
                            if not isinstance(data, dict):
                                raise TypeError()
                            content_type_1_item_type_6 = ContentToolUse.from_dict(data)

                            return content_type_1_item_type_6
                        except (TypeError, ValueError, AttributeError, KeyError):
                            pass
                        if not isinstance(data, dict):
                            raise TypeError()
                        content_type_1_item_type_7 = ContentDocument.from_dict(data)

                        return content_type_1_item_type_7

                    content_type_1_item = _parse_content_type_1_item(
                        content_type_1_item_data
                    )

                    content_type_1.append(content_type_1_item)

                return content_type_1
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(
                list[
                    ContentAudio
                    | ContentData
                    | ContentDocument
                    | ContentImage
                    | ContentReasoning
                    | ContentText
                    | ContentToolUse
                    | ContentVideo
                ]
                | str,
                data,
            )

        content = _parse_content(d.pop("content"))

        def _parse_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        id = _parse_id(d.pop("id", UNSET))

        def _parse_source(
            data: object,
        ) -> ChatMessageAssistantSourceType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                source_type_0 = ChatMessageAssistantSourceType0(data)

                return source_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(ChatMessageAssistantSourceType0 | None | Unset, data)

        source = _parse_source(d.pop("source", UNSET))

        def _parse_metadata(
            data: object,
        ) -> ChatMessageAssistantMetadataType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                metadata_type_0 = ChatMessageAssistantMetadataType0.from_dict(data)

                return metadata_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(ChatMessageAssistantMetadataType0 | None | Unset, data)

        metadata = _parse_metadata(d.pop("metadata", UNSET))

        role = cast(Literal["assistant"] | Unset, d.pop("role", UNSET))
        if role != "assistant" and not isinstance(role, Unset):
            raise ValueError(f"role must match const 'assistant', got '{role}'")

        def _parse_tool_calls(data: object) -> list[ToolCall] | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                tool_calls_type_0 = []
                _tool_calls_type_0 = data
                for tool_calls_type_0_item_data in _tool_calls_type_0:
                    tool_calls_type_0_item = ToolCall.from_dict(
                        tool_calls_type_0_item_data
                    )

                    tool_calls_type_0.append(tool_calls_type_0_item)

                return tool_calls_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(list[ToolCall] | None | Unset, data)

        tool_calls = _parse_tool_calls(d.pop("tool_calls", UNSET))

        def _parse_model(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        model = _parse_model(d.pop("model", UNSET))

        chat_message_assistant = cls(
            content=content,
            id=id,
            source=source,
            metadata=metadata,
            role=role,
            tool_calls=tool_calls,
            model=model,
        )

        chat_message_assistant.additional_properties = d
        return chat_message_assistant

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
