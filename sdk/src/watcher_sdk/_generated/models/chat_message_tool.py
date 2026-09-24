from __future__ import annotations

from collections.abc import Mapping
from typing import (
    TYPE_CHECKING,
    Any,
    Literal,
    TypeVar,
    cast,
)

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.chat_message_tool_source_type_0 import ChatMessageToolSourceType0
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.chat_message_tool_metadata_type_0 import ChatMessageToolMetadataType0
    from ..models.content_audio import ContentAudio
    from ..models.content_data import ContentData
    from ..models.content_document import ContentDocument
    from ..models.content_image import ContentImage
    from ..models.content_reasoning import ContentReasoning
    from ..models.content_text import ContentText
    from ..models.content_tool_use import ContentToolUse
    from ..models.content_video import ContentVideo
    from ..models.tool_call_error import ToolCallError


T = TypeVar("T", bound="ChatMessageTool")


@_attrs_define
class ChatMessageTool:
    """Tool chat message.

    Attributes:
        content (list[ContentAudio | ContentData | ContentDocument | ContentImage | ContentReasoning | ContentText |
            ContentToolUse | ContentVideo] | str):
        id (None | str | Unset):
        source (ChatMessageToolSourceType0 | None | Unset):
        metadata (ChatMessageToolMetadataType0 | None | Unset):
        role (Literal['tool'] | Unset):  Default: 'tool'.
        tool_call_id (None | str | Unset):
        function (None | str | Unset):
        error (None | ToolCallError | Unset):
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
    source: ChatMessageToolSourceType0 | None | Unset = UNSET
    metadata: ChatMessageToolMetadataType0 | None | Unset = UNSET
    role: Literal["tool"] | Unset = "tool"
    tool_call_id: None | str | Unset = UNSET
    function: None | str | Unset = UNSET
    error: None | ToolCallError | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.chat_message_tool_metadata_type_0 import (
            ChatMessageToolMetadataType0,
        )
        from ..models.content_audio import ContentAudio
        from ..models.content_data import ContentData
        from ..models.content_image import ContentImage
        from ..models.content_reasoning import ContentReasoning
        from ..models.content_text import ContentText
        from ..models.content_tool_use import ContentToolUse
        from ..models.content_video import ContentVideo
        from ..models.tool_call_error import ToolCallError

        content: list[dict[str, Any]] | str
        if isinstance(self.content, list):
            content = []
            for content_type_1_item_data in self.content:
                content_type_1_item: dict[str, Any]
                if isinstance(content_type_1_item_data, ContentText):
                    content_type_1_item = content_type_1_item_data.to_dict()
                elif isinstance(content_type_1_item_data, ContentReasoning):
                    content_type_1_item = content_type_1_item_data.to_dict()
                elif isinstance(content_type_1_item_data, ContentImage):
                    content_type_1_item = content_type_1_item_data.to_dict()
                elif isinstance(content_type_1_item_data, ContentAudio):
                    content_type_1_item = content_type_1_item_data.to_dict()
                elif isinstance(content_type_1_item_data, ContentVideo):
                    content_type_1_item = content_type_1_item_data.to_dict()
                elif isinstance(content_type_1_item_data, ContentData):
                    content_type_1_item = content_type_1_item_data.to_dict()
                elif isinstance(content_type_1_item_data, ContentToolUse):
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
        elif isinstance(self.source, ChatMessageToolSourceType0):
            source = self.source.value
        else:
            source = self.source

        metadata: dict[str, Any] | None | Unset
        if isinstance(self.metadata, Unset):
            metadata = UNSET
        elif isinstance(self.metadata, ChatMessageToolMetadataType0):
            metadata = self.metadata.to_dict()
        else:
            metadata = self.metadata

        role = self.role

        tool_call_id: None | str | Unset
        if isinstance(self.tool_call_id, Unset):
            tool_call_id = UNSET
        else:
            tool_call_id = self.tool_call_id

        function: None | str | Unset
        if isinstance(self.function, Unset):
            function = UNSET
        else:
            function = self.function

        error: dict[str, Any] | None | Unset
        if isinstance(self.error, Unset):
            error = UNSET
        elif isinstance(self.error, ToolCallError):
            error = self.error.to_dict()
        else:
            error = self.error

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
        if tool_call_id is not UNSET:
            field_dict["tool_call_id"] = tool_call_id
        if function is not UNSET:
            field_dict["function"] = function
        if error is not UNSET:
            field_dict["error"] = error

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.chat_message_tool_metadata_type_0 import (
            ChatMessageToolMetadataType0,
        )
        from ..models.content_audio import ContentAudio
        from ..models.content_data import ContentData
        from ..models.content_document import ContentDocument
        from ..models.content_image import ContentImage
        from ..models.content_reasoning import ContentReasoning
        from ..models.content_text import ContentText
        from ..models.content_tool_use import ContentToolUse
        from ..models.content_video import ContentVideo
        from ..models.tool_call_error import ToolCallError

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

        def _parse_source(data: object) -> ChatMessageToolSourceType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                source_type_0 = ChatMessageToolSourceType0(data)

                return source_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(ChatMessageToolSourceType0 | None | Unset, data)

        source = _parse_source(d.pop("source", UNSET))

        def _parse_metadata(
            data: object,
        ) -> ChatMessageToolMetadataType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                metadata_type_0 = ChatMessageToolMetadataType0.from_dict(data)

                return metadata_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(ChatMessageToolMetadataType0 | None | Unset, data)

        metadata = _parse_metadata(d.pop("metadata", UNSET))

        role = cast(Literal["tool"] | Unset, d.pop("role", UNSET))
        if role != "tool" and not isinstance(role, Unset):
            raise ValueError(f"role must match const 'tool', got '{role}'")

        def _parse_tool_call_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        tool_call_id = _parse_tool_call_id(d.pop("tool_call_id", UNSET))

        def _parse_function(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        function = _parse_function(d.pop("function", UNSET))

        def _parse_error(data: object) -> None | ToolCallError | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                error_type_0 = ToolCallError.from_dict(data)

                return error_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | ToolCallError | Unset, data)

        error = _parse_error(d.pop("error", UNSET))

        chat_message_tool = cls(
            content=content,
            id=id,
            source=source,
            metadata=metadata,
            role=role,
            tool_call_id=tool_call_id,
            function=function,
            error=error,
        )

        chat_message_tool.additional_properties = d
        return chat_message_tool

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
