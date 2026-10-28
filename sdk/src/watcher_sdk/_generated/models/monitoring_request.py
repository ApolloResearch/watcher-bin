from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Self, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.chat_message_assistant import ChatMessageAssistant
    from ..models.chat_message_system import ChatMessageSystem
    from ..models.chat_message_tool import ChatMessageTool
    from ..models.chat_message_user import ChatMessageUser
    from ..models.monitoring_input import MonitoringInput


T = TypeVar("T", bound="MonitoringRequest")


@_attrs_define
class MonitoringRequest:
    """Request body for POST /v1/monitors/{role}/grade.

    Names *what* to monitor; the server owns *how*. The monitor in the path
    resolves server-side to its prompt, model, reasoning, and context policy,
    and the tool-call audit kind derives from the role.

    Three mutually exclusive payload modes:

    - ``input`` — structured monitoring of one gated tool call: the transcript
      and the call as data, formatted into the monitor prompt server-side.
      The mode clients are expected to use.
    - ``messages`` — pre-assembled message lists, graded as sent.
    - ``trajectory_ids`` + ``session_id`` — DB-backed grading of stored
      trajectories.

    On the two ephemeral modes the caller may also send ``session_id`` +
    ``tool_use_id`` to identify the gated call being graded (the role's run
    kind makes every ephemeral grade here a tool-call audit row).

        Attributes:
            trajectory_ids (list[str] | None | Unset):
            session_id (None | str | Unset):
            messages (list[list[ChatMessageAssistant | ChatMessageSystem | ChatMessageTool | ChatMessageUser]] | None |
                Unset):
            tool_use_id (None | str | Unset):
            input_ (MonitoringInput | None | Unset):
    """

    trajectory_ids: list[str] | None | Unset = UNSET
    session_id: None | str | Unset = UNSET
    messages: (
        list[
            list[
                ChatMessageAssistant
                | ChatMessageSystem
                | ChatMessageTool
                | ChatMessageUser
            ]
        ]
        | None
        | Unset
    ) = UNSET
    tool_use_id: None | str | Unset = UNSET
    input_: MonitoringInput | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.chat_message_assistant import ChatMessageAssistant
        from ..models.chat_message_system import ChatMessageSystem
        from ..models.chat_message_user import ChatMessageUser
        from ..models.monitoring_input import MonitoringInput

        trajectory_ids: list[str] | None | Unset
        if isinstance(self.trajectory_ids, Unset):
            trajectory_ids = UNSET
        elif isinstance(self.trajectory_ids, list):
            trajectory_ids = self.trajectory_ids

        else:
            trajectory_ids = self.trajectory_ids

        session_id: None | str | Unset
        if isinstance(self.session_id, Unset):
            session_id = UNSET
        else:
            session_id = self.session_id

        messages: list[list[dict[str, Any]]] | None | Unset
        if isinstance(self.messages, Unset):
            messages = UNSET
        elif isinstance(self.messages, list):
            messages = []
            for messages_type_0_item_data in self.messages:
                messages_type_0_item = []
                for messages_type_0_item_item_data in messages_type_0_item_data:
                    messages_type_0_item_item: dict[str, Any]
                    if (
                        isinstance(messages_type_0_item_item_data, ChatMessageSystem)
                        or isinstance(messages_type_0_item_item_data, ChatMessageUser)
                        or isinstance(
                            messages_type_0_item_item_data, ChatMessageAssistant
                        )
                    ):
                        messages_type_0_item_item = (
                            messages_type_0_item_item_data.to_dict()
                        )
                    else:
                        messages_type_0_item_item = (
                            messages_type_0_item_item_data.to_dict()
                        )

                    messages_type_0_item.append(messages_type_0_item_item)

                messages.append(messages_type_0_item)

        else:
            messages = self.messages

        tool_use_id: None | str | Unset
        if isinstance(self.tool_use_id, Unset):
            tool_use_id = UNSET
        else:
            tool_use_id = self.tool_use_id

        input_: dict[str, Any] | None | Unset
        if isinstance(self.input_, Unset):
            input_ = UNSET
        elif isinstance(self.input_, MonitoringInput):
            input_ = self.input_.to_dict()
        else:
            input_ = self.input_

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if trajectory_ids is not UNSET:
            field_dict["trajectory_ids"] = trajectory_ids
        if session_id is not UNSET:
            field_dict["session_id"] = session_id
        if messages is not UNSET:
            field_dict["messages"] = messages
        if tool_use_id is not UNSET:
            field_dict["tool_use_id"] = tool_use_id
        if input_ is not UNSET:
            field_dict["input"] = input_

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        from ..models.chat_message_assistant import ChatMessageAssistant
        from ..models.chat_message_system import ChatMessageSystem
        from ..models.chat_message_tool import ChatMessageTool
        from ..models.chat_message_user import ChatMessageUser
        from ..models.monitoring_input import MonitoringInput

        d = dict(src_dict)

        def _parse_trajectory_ids(data: object) -> list[str] | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                trajectory_ids_type_0 = cast(list[str], data)

                return trajectory_ids_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(list[str] | None | Unset, data)

        trajectory_ids = _parse_trajectory_ids(d.pop("trajectory_ids", UNSET))

        def _parse_session_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        session_id = _parse_session_id(d.pop("session_id", UNSET))

        def _parse_messages(
            data: object,
        ) -> (
            list[
                list[
                    ChatMessageAssistant
                    | ChatMessageSystem
                    | ChatMessageTool
                    | ChatMessageUser
                ]
            ]
            | None
            | Unset
        ):
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                messages_type_0 = []
                _messages_type_0 = data
                for messages_type_0_item_data in _messages_type_0:
                    messages_type_0_item = []
                    _messages_type_0_item = messages_type_0_item_data
                    for messages_type_0_item_item_data in _messages_type_0_item:

                        def _parse_messages_type_0_item_item(
                            data: object,
                        ) -> (
                            ChatMessageAssistant
                            | ChatMessageSystem
                            | ChatMessageTool
                            | ChatMessageUser
                        ):
                            try:
                                if not isinstance(data, dict):
                                    raise TypeError()
                                messages_type_0_item_item_type_0 = (
                                    ChatMessageSystem.from_dict(data)
                                )

                                return messages_type_0_item_item_type_0
                            except (TypeError, ValueError, AttributeError, KeyError):
                                pass
                            try:
                                if not isinstance(data, dict):
                                    raise TypeError()
                                messages_type_0_item_item_type_1 = (
                                    ChatMessageUser.from_dict(data)
                                )

                                return messages_type_0_item_item_type_1
                            except (TypeError, ValueError, AttributeError, KeyError):
                                pass
                            try:
                                if not isinstance(data, dict):
                                    raise TypeError()
                                messages_type_0_item_item_type_2 = (
                                    ChatMessageAssistant.from_dict(data)
                                )

                                return messages_type_0_item_item_type_2
                            except (TypeError, ValueError, AttributeError, KeyError):
                                pass
                            if not isinstance(data, dict):
                                raise TypeError()
                            messages_type_0_item_item_type_3 = (
                                ChatMessageTool.from_dict(data)
                            )

                            return messages_type_0_item_item_type_3

                        messages_type_0_item_item = _parse_messages_type_0_item_item(
                            messages_type_0_item_item_data
                        )

                        messages_type_0_item.append(messages_type_0_item_item)

                    messages_type_0.append(messages_type_0_item)

                return messages_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(
                list[
                    list[
                        ChatMessageAssistant
                        | ChatMessageSystem
                        | ChatMessageTool
                        | ChatMessageUser
                    ]
                ]
                | None
                | Unset,
                data,
            )

        messages = _parse_messages(d.pop("messages", UNSET))

        def _parse_tool_use_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        tool_use_id = _parse_tool_use_id(d.pop("tool_use_id", UNSET))

        def _parse_input_(data: object) -> MonitoringInput | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                input_type_0 = MonitoringInput.from_dict(data)

                return input_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(MonitoringInput | None | Unset, data)

        input_ = _parse_input_(d.pop("input", UNSET))

        monitoring_request = cls(
            trajectory_ids=trajectory_ids,
            session_id=session_id,
            messages=messages,
            tool_use_id=tool_use_id,
            input_=input_,
        )

        monitoring_request.additional_properties = d
        return monitoring_request

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
