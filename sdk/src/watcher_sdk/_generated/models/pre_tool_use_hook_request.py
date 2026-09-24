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

from ..models.pre_tool_use_hook_request_mode import PreToolUseHookRequestMode
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.chat_message_assistant import ChatMessageAssistant
    from ..models.chat_message_system import ChatMessageSystem
    from ..models.chat_message_tool import ChatMessageTool
    from ..models.chat_message_user import ChatMessageUser
    from ..models.monitoring_input import MonitoringInput
    from ..models.pre_tool_use_hook_request_external_ids_type_0 import (
        PreToolUseHookRequestExternalIdsType0,
    )
    from ..models.pre_tool_use_hook_request_settings_overrides_type_1 import (
        PreToolUseHookRequestSettingsOverridesType1,
    )


T = TypeVar("T", bound="PreToolUseHookRequest")


@_attrs_define
class PreToolUseHookRequest:
    """Evaluate pending tool calls or ingest a transcript through the generic hook.

    Send the conversation once in `messages` and select pending calls with
    `input`. A scalar input returns one response; a list returns one outcome
    per input in the same order, including each input's `tool_use_id`. Null,
    omitted, or empty-list input ingests the transcript without grading or
    writing decisions and returns an empty list, regardless of enforcement mode.
    Named observe calls return completed judgments with a deferred applied
    decision. Enforce and observe support ephemeral evaluation and evaluation
    without session-write permission; recording requires that permission.
    All calls share one transcript, which is ingested once when recording is enabled.

    Input lists accept at most 32 items, including blank or ephemeral inputs.
    Larger lists are rejected with HTTP 422 before ingestion or grading.
    Batches with multiple inputs require top-level `messages`. Their inputs
    must omit `messages` or supply null or an empty list, so the transcript is
    sent only once. Scalars and single-item lists may supply `input.messages`;
    if both locations are non-null, their transcripts must match. An input
    with an explicitly blank tool name only ingests and retains its response shape.
    Paused and unnamed inputs need no grading admission;
    authorized ingestion still uses normal database resources.

    Send structured `messages`, including the assistant message containing each
    pending call. Pre-rendered `transcript` and caller `triage_assessment` are
    rejected. A recorded named call requires `input.tool_use_id` matching one
    call in those messages; different batch inputs must name different ids.
    The selected tool name and arguments must match every transcript occurrence
    of its ID. Argument object key order is ignored; JSON value types and string
    content must agree. Omitted `tool_input` matches an empty arguments object;
    explicit null does not. Mismatches return HTTP 422 before grading or ingestion.
    `ephemeral` suppresses transcript, decision, and grade persistence, but not
    usage. Enforce and observe requests may both use it.

    `external_ids` includes each distinct conversation ID from the harness
    and gateway, including a separate gateway-issued ID when available.
    A null value explicitly opts into transcript-prefix
    reconciliation and still names the harness. Recorded requests require this
    mapping. `user` supplies the developer email only when the authenticated
    caller can impersonate; otherwise attribution stays with that caller.

    `settings_overrides` accepts a YAML string or JSON object that the server
    will merge onto administrator settings as a local settings layer.
    Administrator locks reject overrides with HTTP 422, even when they repeat
    a locked value. Set `enforcement.mode` there for observe or paused behavior;
    omitted overrides inherit the administrator's settings. A gateway's
    server-owned capability limit independently prevents unsupported enforcement.

    `mode=triage_only` bounds grading depth: triage can allow but cannot deny;
    otherwise it escalates without running the gateway monitor. `skip_rules`
    is for clients that already evaluated deterministic stages. When they send
    `policy_version` (`<version>@<builtin digest>`), a stale token forces those
    stages to run again against the server's current policy.

        Attributes:
            format_ (Literal['watcher']):
            input_ (list[MonitoringInput] | MonitoringInput | None | Unset):
            messages (list[ChatMessageAssistant | ChatMessageSystem | ChatMessageTool | ChatMessageUser] | None | Unset):
                Shared conversation transcript. Required for zero or multiple inputs; a scalar or single-item list may supply
                input.messages instead.
            mode (PreToolUseHookRequestMode | Unset):  Default: PreToolUseHookRequestMode.FULL.
            external_ids (None | PreToolUseHookRequestExternalIdsType0 | Unset): Distinct conversation IDs from the harness
                and gateway, keyed by source. Required unless ephemeral is true; send every id you have, e.g. {"claude_code":
                "<Claude Code session uuid>", "other": "<your own conversation id>"}. The keys also name the harness. A caller
                with no id at all records id-less by sending an explicit null value, e.g. {"other": null} or {"claude_code":
                null}: the session is then found by transcript prefix.
            user (None | str | Unset):
            ephemeral (bool | Unset):  Default: False.
            force_regrade (bool | Unset): Evaluate again even when this session and tool-use ID have a completed judgment.
                The new result may replace the recorded decision, including in observe mode. Otherwise a readable completed
                judgment with matching tool arguments is reused, regardless of policy version, under the current enforcement
                posture. Default: False.
            skip_rules (bool | Unset):  Default: False.
            policy_version (None | str | Unset):
            settings_overrides (None | PreToolUseHookRequestSettingsOverridesType1 | str | Unset): Per-request settings as
                YAML or a JSON object; at most 65,536 characters of YAML or serialized JSON. Administrator permission locks
                apply.
    """

    format_: Literal["watcher"]
    input_: list[MonitoringInput] | MonitoringInput | None | Unset = UNSET
    messages: (
        list[
            ChatMessageAssistant | ChatMessageSystem | ChatMessageTool | ChatMessageUser
        ]
        | None
        | Unset
    ) = UNSET
    mode: PreToolUseHookRequestMode | Unset = PreToolUseHookRequestMode.FULL
    external_ids: None | PreToolUseHookRequestExternalIdsType0 | Unset = UNSET
    user: None | str | Unset = UNSET
    ephemeral: bool | Unset = False
    force_regrade: bool | Unset = False
    skip_rules: bool | Unset = False
    policy_version: None | str | Unset = UNSET
    settings_overrides: (
        None | PreToolUseHookRequestSettingsOverridesType1 | str | Unset
    ) = UNSET

    def to_dict(self) -> dict[str, Any]:
        from ..models.chat_message_assistant import ChatMessageAssistant
        from ..models.chat_message_system import ChatMessageSystem
        from ..models.chat_message_user import ChatMessageUser
        from ..models.monitoring_input import MonitoringInput
        from ..models.pre_tool_use_hook_request_external_ids_type_0 import (
            PreToolUseHookRequestExternalIdsType0,
        )
        from ..models.pre_tool_use_hook_request_settings_overrides_type_1 import (
            PreToolUseHookRequestSettingsOverridesType1,
        )

        format_ = self.format_

        input_: dict[str, Any] | list[dict[str, Any]] | None | Unset
        if isinstance(self.input_, Unset):
            input_ = UNSET
        elif isinstance(self.input_, MonitoringInput):
            input_ = self.input_.to_dict()
        elif isinstance(self.input_, list):
            input_ = []
            for input_type_1_item_data in self.input_:
                input_type_1_item = input_type_1_item_data.to_dict()
                input_.append(input_type_1_item)

        else:
            input_ = self.input_

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

        mode: str | Unset = UNSET
        if not isinstance(self.mode, Unset):
            mode = self.mode.value

        external_ids: dict[str, Any] | None | Unset
        if isinstance(self.external_ids, Unset):
            external_ids = UNSET
        elif isinstance(self.external_ids, PreToolUseHookRequestExternalIdsType0):
            external_ids = self.external_ids.to_dict()
        else:
            external_ids = self.external_ids

        user: None | str | Unset
        if isinstance(self.user, Unset):
            user = UNSET
        else:
            user = self.user

        ephemeral = self.ephemeral

        force_regrade = self.force_regrade

        skip_rules = self.skip_rules

        policy_version: None | str | Unset
        if isinstance(self.policy_version, Unset):
            policy_version = UNSET
        else:
            policy_version = self.policy_version

        settings_overrides: dict[str, Any] | None | str | Unset
        if isinstance(self.settings_overrides, Unset):
            settings_overrides = UNSET
        elif isinstance(
            self.settings_overrides, PreToolUseHookRequestSettingsOverridesType1
        ):
            settings_overrides = self.settings_overrides.to_dict()
        else:
            settings_overrides = self.settings_overrides

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "format": format_,
            }
        )
        if input_ is not UNSET:
            field_dict["input"] = input_
        if messages is not UNSET:
            field_dict["messages"] = messages
        if mode is not UNSET:
            field_dict["mode"] = mode
        if external_ids is not UNSET:
            field_dict["external_ids"] = external_ids
        if user is not UNSET:
            field_dict["user"] = user
        if ephemeral is not UNSET:
            field_dict["ephemeral"] = ephemeral
        if force_regrade is not UNSET:
            field_dict["force_regrade"] = force_regrade
        if skip_rules is not UNSET:
            field_dict["skip_rules"] = skip_rules
        if policy_version is not UNSET:
            field_dict["policy_version"] = policy_version
        if settings_overrides is not UNSET:
            field_dict["settings_overrides"] = settings_overrides

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.chat_message_assistant import ChatMessageAssistant
        from ..models.chat_message_system import ChatMessageSystem
        from ..models.chat_message_tool import ChatMessageTool
        from ..models.chat_message_user import ChatMessageUser
        from ..models.monitoring_input import MonitoringInput
        from ..models.pre_tool_use_hook_request_external_ids_type_0 import (
            PreToolUseHookRequestExternalIdsType0,
        )
        from ..models.pre_tool_use_hook_request_settings_overrides_type_1 import (
            PreToolUseHookRequestSettingsOverridesType1,
        )

        d = dict(src_dict)
        format_ = cast(Literal["watcher"], d.pop("format"))
        if format_ != "watcher":
            raise ValueError(f"format must match const 'watcher', got '{format_}'")

        def _parse_input_(
            data: object,
        ) -> list[MonitoringInput] | MonitoringInput | None | Unset:
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
            try:
                if not isinstance(data, list):
                    raise TypeError()
                input_type_1 = []
                _input_type_1 = data
                for input_type_1_item_data in _input_type_1:
                    input_type_1_item = MonitoringInput.from_dict(
                        input_type_1_item_data
                    )

                    input_type_1.append(input_type_1_item)

                return input_type_1
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(list[MonitoringInput] | MonitoringInput | None | Unset, data)

        input_ = _parse_input_(d.pop("input", UNSET))

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

        _mode = d.pop("mode", UNSET)
        mode: PreToolUseHookRequestMode | Unset
        if isinstance(_mode, Unset):
            mode = UNSET
        else:
            mode = PreToolUseHookRequestMode(_mode)

        def _parse_external_ids(
            data: object,
        ) -> None | PreToolUseHookRequestExternalIdsType0 | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                external_ids_type_0 = PreToolUseHookRequestExternalIdsType0.from_dict(
                    data
                )

                return external_ids_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | PreToolUseHookRequestExternalIdsType0 | Unset, data)

        external_ids = _parse_external_ids(d.pop("external_ids", UNSET))

        def _parse_user(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        user = _parse_user(d.pop("user", UNSET))

        ephemeral = d.pop("ephemeral", UNSET)

        force_regrade = d.pop("force_regrade", UNSET)

        skip_rules = d.pop("skip_rules", UNSET)

        def _parse_policy_version(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        policy_version = _parse_policy_version(d.pop("policy_version", UNSET))

        def _parse_settings_overrides(
            data: object,
        ) -> None | PreToolUseHookRequestSettingsOverridesType1 | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                settings_overrides_type_1 = (
                    PreToolUseHookRequestSettingsOverridesType1.from_dict(data)
                )

                return settings_overrides_type_1
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(
                None | PreToolUseHookRequestSettingsOverridesType1 | str | Unset, data
            )

        settings_overrides = _parse_settings_overrides(
            d.pop("settings_overrides", UNSET)
        )

        pre_tool_use_hook_request = cls(
            format_=format_,
            input_=input_,
            messages=messages,
            mode=mode,
            external_ids=external_ids,
            user=user,
            ephemeral=ephemeral,
            force_regrade=force_regrade,
            skip_rules=skip_rules,
            policy_version=policy_version,
            settings_overrides=settings_overrides,
        )

        return pre_tool_use_hook_request
