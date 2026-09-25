from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.chat_message_assistant import ChatMessageAssistant
    from ..models.chat_message_system import ChatMessageSystem
    from ..models.chat_message_tool import ChatMessageTool
    from ..models.chat_message_user import ChatMessageUser
    from ..models.prior_human_decision import PriorHumanDecision
    from ..models.triage_assessment import TriageAssessment


T = TypeVar("T", bound="MonitoringInput")


@_attrs_define
class MonitoringInput:
    """Structured inputs for monitoring one gated tool call.

    The caller sends *what the monitor looks at*; the server owns how it is
    formatted into a prompt, so prompt structure can change without a client
    release.

    The conversation context is ``messages`` — the transcript as structured
    ``ChatMessage`` objects. The server applies the monitor's served
    context policy (user-message window, tool outputs / agent reasoning
    withheld) and renders the prompt, so a caller sends its conversation
    without reimplementing the calibrated renderer. When both forms are sent
    ``messages`` wins.

    ``transcript`` — the same context as pre-rendered per-message text parts,
    rendered client-side — is deprecated: current clients send only
    ``messages`` (a client is never newer than its server), so the form exists
    for clients that predate structured messages and is dropped once the
    compatibility window moves past them.

    ``grading_guidelines`` is the watched repository's own guidelines document
    (e.g. WATCHER.md), included verbatim as caller-side data.

        Attributes:
            tool_name (str):
            messages (list[ChatMessageAssistant | ChatMessageSystem | ChatMessageTool | ChatMessageUser] | None | Unset):
            transcript (list[str] | Unset):
            tool_use_id (None | str | Unset): Identifies the pending call for hook requests. Monitor grade linkage uses the
                request's top-level tool_use_id instead.
            tool_input (Any | Unset):
            cwd (None | str | Unset):
            triage_assessment (None | TriageAssessment | Unset):
            prior_decisions (list[PriorHumanDecision] | Unset):
            grading_guidelines (None | str | Unset):
    """

    tool_name: str
    messages: (
        list[
            ChatMessageAssistant | ChatMessageSystem | ChatMessageTool | ChatMessageUser
        ]
        | None
        | Unset
    ) = UNSET
    transcript: list[str] | Unset = UNSET
    tool_use_id: None | str | Unset = UNSET
    tool_input: Any | Unset = UNSET
    cwd: None | str | Unset = UNSET
    triage_assessment: None | TriageAssessment | Unset = UNSET
    prior_decisions: list[PriorHumanDecision] | Unset = UNSET
    grading_guidelines: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.chat_message_assistant import ChatMessageAssistant
        from ..models.chat_message_system import ChatMessageSystem
        from ..models.chat_message_user import ChatMessageUser
        from ..models.triage_assessment import TriageAssessment

        tool_name = self.tool_name

        messages: list[dict[str, Any]] | None | Unset
        if isinstance(self.messages, Unset):
            messages = UNSET
        elif isinstance(self.messages, list):
            messages = []
            for messages_type_0_item_data in self.messages:
                messages_type_0_item: dict[str, Any]
                if isinstance(messages_type_0_item_data, ChatMessageSystem):
                    messages_type_0_item = messages_type_0_item_data.to_dict()
                elif isinstance(messages_type_0_item_data, ChatMessageUser):
                    messages_type_0_item = messages_type_0_item_data.to_dict()
                elif isinstance(messages_type_0_item_data, ChatMessageAssistant):
                    messages_type_0_item = messages_type_0_item_data.to_dict()
                else:
                    messages_type_0_item = messages_type_0_item_data.to_dict()

                messages.append(messages_type_0_item)

        else:
            messages = self.messages

        transcript: list[str] | Unset = UNSET
        if not isinstance(self.transcript, Unset):
            transcript = self.transcript

        tool_use_id: None | str | Unset
        if isinstance(self.tool_use_id, Unset):
            tool_use_id = UNSET
        else:
            tool_use_id = self.tool_use_id

        tool_input = self.tool_input

        cwd: None | str | Unset
        if isinstance(self.cwd, Unset):
            cwd = UNSET
        else:
            cwd = self.cwd

        triage_assessment: dict[str, Any] | None | Unset
        if isinstance(self.triage_assessment, Unset):
            triage_assessment = UNSET
        elif isinstance(self.triage_assessment, TriageAssessment):
            triage_assessment = self.triage_assessment.to_dict()
        else:
            triage_assessment = self.triage_assessment

        prior_decisions: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.prior_decisions, Unset):
            prior_decisions = []
            for prior_decisions_item_data in self.prior_decisions:
                prior_decisions_item = prior_decisions_item_data.to_dict()
                prior_decisions.append(prior_decisions_item)

        grading_guidelines: None | str | Unset
        if isinstance(self.grading_guidelines, Unset):
            grading_guidelines = UNSET
        else:
            grading_guidelines = self.grading_guidelines

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "tool_name": tool_name,
            }
        )
        if messages is not UNSET:
            field_dict["messages"] = messages
        if transcript is not UNSET:
            field_dict["transcript"] = transcript
        if tool_use_id is not UNSET:
            field_dict["tool_use_id"] = tool_use_id
        if tool_input is not UNSET:
            field_dict["tool_input"] = tool_input
        if cwd is not UNSET:
            field_dict["cwd"] = cwd
        if triage_assessment is not UNSET:
            field_dict["triage_assessment"] = triage_assessment
        if prior_decisions is not UNSET:
            field_dict["prior_decisions"] = prior_decisions
        if grading_guidelines is not UNSET:
            field_dict["grading_guidelines"] = grading_guidelines

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.chat_message_assistant import ChatMessageAssistant
        from ..models.chat_message_system import ChatMessageSystem
        from ..models.chat_message_tool import ChatMessageTool
        from ..models.chat_message_user import ChatMessageUser
        from ..models.prior_human_decision import PriorHumanDecision
        from ..models.triage_assessment import TriageAssessment

        d = dict(src_dict)
        tool_name = d.pop("tool_name")

        def _parse_messages(
            data: object,
        ) -> (
            list[
                ChatMessageAssistant
                | ChatMessageSystem
                | ChatMessageTool
                | ChatMessageUser
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

                    def _parse_messages_type_0_item(
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
                            messages_type_0_item_type_0 = ChatMessageSystem.from_dict(
                                data
                            )

                            return messages_type_0_item_type_0
                        except (TypeError, ValueError, AttributeError, KeyError):
                            pass
                        try:
                            if not isinstance(data, dict):
                                raise TypeError()
                            messages_type_0_item_type_1 = ChatMessageUser.from_dict(
                                data
                            )

                            return messages_type_0_item_type_1
                        except (TypeError, ValueError, AttributeError, KeyError):
                            pass
                        try:
                            if not isinstance(data, dict):
                                raise TypeError()
                            messages_type_0_item_type_2 = (
                                ChatMessageAssistant.from_dict(data)
                            )

                            return messages_type_0_item_type_2
                        except (TypeError, ValueError, AttributeError, KeyError):
                            pass
                        if not isinstance(data, dict):
                            raise TypeError()
                        messages_type_0_item_type_3 = ChatMessageTool.from_dict(data)

                        return messages_type_0_item_type_3

                    messages_type_0_item = _parse_messages_type_0_item(
                        messages_type_0_item_data
                    )

                    messages_type_0.append(messages_type_0_item)

                return messages_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(
                list[
                    ChatMessageAssistant
                    | ChatMessageSystem
                    | ChatMessageTool
                    | ChatMessageUser
                ]
                | None
                | Unset,
                data,
            )

        messages = _parse_messages(d.pop("messages", UNSET))

        transcript = cast(list[str], d.pop("transcript", UNSET))

        def _parse_tool_use_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        tool_use_id = _parse_tool_use_id(d.pop("tool_use_id", UNSET))

        tool_input = d.pop("tool_input", UNSET)

        def _parse_cwd(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        cwd = _parse_cwd(d.pop("cwd", UNSET))

        def _parse_triage_assessment(data: object) -> None | TriageAssessment | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                triage_assessment_type_0 = TriageAssessment.from_dict(data)

                return triage_assessment_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | TriageAssessment | Unset, data)

        triage_assessment = _parse_triage_assessment(d.pop("triage_assessment", UNSET))

        _prior_decisions = d.pop("prior_decisions", UNSET)
        prior_decisions: list[PriorHumanDecision] | Unset = UNSET
        if _prior_decisions is not UNSET:
            prior_decisions = []
            for prior_decisions_item_data in _prior_decisions:
                prior_decisions_item = PriorHumanDecision.from_dict(
                    prior_decisions_item_data
                )

                prior_decisions.append(prior_decisions_item)

        def _parse_grading_guidelines(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        grading_guidelines = _parse_grading_guidelines(
            d.pop("grading_guidelines", UNSET)
        )

        monitoring_input = cls(
            tool_name=tool_name,
            messages=messages,
            transcript=transcript,
            tool_use_id=tool_use_id,
            tool_input=tool_input,
            cwd=cwd,
            triage_assessment=triage_assessment,
            prior_decisions=prior_decisions,
            grading_guidelines=grading_guidelines,
        )

        monitoring_input.additional_properties = d
        return monitoring_input

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
