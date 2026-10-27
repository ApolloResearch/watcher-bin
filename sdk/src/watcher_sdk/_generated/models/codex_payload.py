from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from typing_extensions import Self

from ..models.codex_payload_type_type_0 import CodexPayloadTypeType0
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.codex_content_item import CodexContentItem
    from ..models.codex_git_info import CodexGitInfo
    from ..models.codex_local_shell_action import CodexLocalShellAction
    from ..models.codex_payload_arguments_type_1 import CodexPayloadArgumentsType1
    from ..models.codex_payload_input_type_1 import CodexPayloadInputType1
    from ..models.codex_reasoning_summary_item import CodexReasoningSummaryItem


T = TypeVar("T", bound="CodexPayload")


@_attrs_define
class CodexPayload:
    """All payload fields the Codex JSONL parser reads, in one class with every field optional.

    Handlers check ``type`` to know which fields are set. The ``type``
    annotation lists the values the parser handles; unknown values still parse
    (the ``| str`` branch) and are skipped with a logged warning.

    Validators normalise a few looser shapes so every field has one type, as
    ``ClaudeCodeEntry`` does for Claude Code transcripts.

        Attributes:
            type_ (CodexPayloadTypeType0 | None | str | Unset):
            role (None | str | Unset):
            content (list[CodexContentItem] | None | str | Unset):
            summary (list[CodexReasoningSummaryItem] | None | Unset):
            encrypted_content (None | str | Unset):
            name (None | str | Unset):
            namespace (None | str | Unset):
            call_id (None | str | Unset):
            arguments (CodexPayloadArgumentsType1 | None | str | Unset):
            output (list[CodexContentItem] | None | str | Unset):
            action (CodexLocalShellAction | None | Unset):
            input_ (CodexPayloadInputType1 | None | str | Unset):
            model (None | str | Unset):
            user_instructions (None | str | Unset):
            developer_instructions (None | str | Unset):
            id (None | str | Unset):
            subagent_history_start_ordinal (int | None | Unset):
            cwd (None | str | Unset):
            cli_version (None | str | Unset):
            originator (None | str | Unset):
            git (CodexGitInfo | None | Unset):
            message (None | str | Unset):
            replacement_history (list[CodexPayload] | None | Unset):
    """

    type_: CodexPayloadTypeType0 | None | str | Unset = UNSET
    role: None | str | Unset = UNSET
    content: list[CodexContentItem] | None | str | Unset = UNSET
    summary: list[CodexReasoningSummaryItem] | None | Unset = UNSET
    encrypted_content: None | str | Unset = UNSET
    name: None | str | Unset = UNSET
    namespace: None | str | Unset = UNSET
    call_id: None | str | Unset = UNSET
    arguments: CodexPayloadArgumentsType1 | None | str | Unset = UNSET
    output: list[CodexContentItem] | None | str | Unset = UNSET
    action: CodexLocalShellAction | None | Unset = UNSET
    input_: CodexPayloadInputType1 | None | str | Unset = UNSET
    model: None | str | Unset = UNSET
    user_instructions: None | str | Unset = UNSET
    developer_instructions: None | str | Unset = UNSET
    id: None | str | Unset = UNSET
    subagent_history_start_ordinal: int | None | Unset = UNSET
    cwd: None | str | Unset = UNSET
    cli_version: None | str | Unset = UNSET
    originator: None | str | Unset = UNSET
    git: CodexGitInfo | None | Unset = UNSET
    message: None | str | Unset = UNSET
    replacement_history: list[CodexPayload] | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.codex_git_info import CodexGitInfo
        from ..models.codex_local_shell_action import CodexLocalShellAction
        from ..models.codex_payload_arguments_type_1 import CodexPayloadArgumentsType1
        from ..models.codex_payload_input_type_1 import CodexPayloadInputType1

        type_: None | str | Unset
        if isinstance(self.type_, Unset):
            type_ = UNSET
        elif isinstance(self.type_, CodexPayloadTypeType0):
            type_ = self.type_.value
        else:
            type_ = self.type_

        role: None | str | Unset
        if isinstance(self.role, Unset):
            role = UNSET
        else:
            role = self.role

        content: list[dict[str, Any]] | None | str | Unset
        if isinstance(self.content, Unset):
            content = UNSET
        elif isinstance(self.content, list):
            content = []
            for content_type_0_item_data in self.content:
                content_type_0_item = content_type_0_item_data.to_dict()
                content.append(content_type_0_item)

        else:
            content = self.content

        summary: list[dict[str, Any]] | None | Unset
        if isinstance(self.summary, Unset):
            summary = UNSET
        elif isinstance(self.summary, list):
            summary = []
            for summary_type_0_item_data in self.summary:
                summary_type_0_item = summary_type_0_item_data.to_dict()
                summary.append(summary_type_0_item)

        else:
            summary = self.summary

        encrypted_content: None | str | Unset
        if isinstance(self.encrypted_content, Unset):
            encrypted_content = UNSET
        else:
            encrypted_content = self.encrypted_content

        name: None | str | Unset
        if isinstance(self.name, Unset):
            name = UNSET
        else:
            name = self.name

        namespace: None | str | Unset
        if isinstance(self.namespace, Unset):
            namespace = UNSET
        else:
            namespace = self.namespace

        call_id: None | str | Unset
        if isinstance(self.call_id, Unset):
            call_id = UNSET
        else:
            call_id = self.call_id

        arguments: dict[str, Any] | None | str | Unset
        if isinstance(self.arguments, Unset):
            arguments = UNSET
        elif isinstance(self.arguments, CodexPayloadArgumentsType1):
            arguments = self.arguments.to_dict()
        else:
            arguments = self.arguments

        output: list[dict[str, Any]] | None | str | Unset
        if isinstance(self.output, Unset):
            output = UNSET
        elif isinstance(self.output, list):
            output = []
            for output_type_1_item_data in self.output:
                output_type_1_item = output_type_1_item_data.to_dict()
                output.append(output_type_1_item)

        else:
            output = self.output

        action: dict[str, Any] | None | Unset
        if isinstance(self.action, Unset):
            action = UNSET
        elif isinstance(self.action, CodexLocalShellAction):
            action = self.action.to_dict()
        else:
            action = self.action

        input_: dict[str, Any] | None | str | Unset
        if isinstance(self.input_, Unset):
            input_ = UNSET
        elif isinstance(self.input_, CodexPayloadInputType1):
            input_ = self.input_.to_dict()
        else:
            input_ = self.input_

        model: None | str | Unset
        if isinstance(self.model, Unset):
            model = UNSET
        else:
            model = self.model

        user_instructions: None | str | Unset
        if isinstance(self.user_instructions, Unset):
            user_instructions = UNSET
        else:
            user_instructions = self.user_instructions

        developer_instructions: None | str | Unset
        if isinstance(self.developer_instructions, Unset):
            developer_instructions = UNSET
        else:
            developer_instructions = self.developer_instructions

        id: None | str | Unset
        if isinstance(self.id, Unset):
            id = UNSET
        else:
            id = self.id

        subagent_history_start_ordinal: int | None | Unset
        if isinstance(self.subagent_history_start_ordinal, Unset):
            subagent_history_start_ordinal = UNSET
        else:
            subagent_history_start_ordinal = self.subagent_history_start_ordinal

        cwd: None | str | Unset
        if isinstance(self.cwd, Unset):
            cwd = UNSET
        else:
            cwd = self.cwd

        cli_version: None | str | Unset
        if isinstance(self.cli_version, Unset):
            cli_version = UNSET
        else:
            cli_version = self.cli_version

        originator: None | str | Unset
        if isinstance(self.originator, Unset):
            originator = UNSET
        else:
            originator = self.originator

        git: dict[str, Any] | None | Unset
        if isinstance(self.git, Unset):
            git = UNSET
        elif isinstance(self.git, CodexGitInfo):
            git = self.git.to_dict()
        else:
            git = self.git

        message: None | str | Unset
        if isinstance(self.message, Unset):
            message = UNSET
        else:
            message = self.message

        replacement_history: list[dict[str, Any]] | None | Unset
        if isinstance(self.replacement_history, Unset):
            replacement_history = UNSET
        elif isinstance(self.replacement_history, list):
            replacement_history = []
            for replacement_history_type_0_item_data in self.replacement_history:
                replacement_history_type_0_item = (
                    replacement_history_type_0_item_data.to_dict()
                )
                replacement_history.append(replacement_history_type_0_item)

        else:
            replacement_history = self.replacement_history

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if type_ is not UNSET:
            field_dict["type"] = type_
        if role is not UNSET:
            field_dict["role"] = role
        if content is not UNSET:
            field_dict["content"] = content
        if summary is not UNSET:
            field_dict["summary"] = summary
        if encrypted_content is not UNSET:
            field_dict["encrypted_content"] = encrypted_content
        if name is not UNSET:
            field_dict["name"] = name
        if namespace is not UNSET:
            field_dict["namespace"] = namespace
        if call_id is not UNSET:
            field_dict["call_id"] = call_id
        if arguments is not UNSET:
            field_dict["arguments"] = arguments
        if output is not UNSET:
            field_dict["output"] = output
        if action is not UNSET:
            field_dict["action"] = action
        if input_ is not UNSET:
            field_dict["input"] = input_
        if model is not UNSET:
            field_dict["model"] = model
        if user_instructions is not UNSET:
            field_dict["user_instructions"] = user_instructions
        if developer_instructions is not UNSET:
            field_dict["developer_instructions"] = developer_instructions
        if id is not UNSET:
            field_dict["id"] = id
        if subagent_history_start_ordinal is not UNSET:
            field_dict["subagent_history_start_ordinal"] = (
                subagent_history_start_ordinal
            )
        if cwd is not UNSET:
            field_dict["cwd"] = cwd
        if cli_version is not UNSET:
            field_dict["cli_version"] = cli_version
        if originator is not UNSET:
            field_dict["originator"] = originator
        if git is not UNSET:
            field_dict["git"] = git
        if message is not UNSET:
            field_dict["message"] = message
        if replacement_history is not UNSET:
            field_dict["replacement_history"] = replacement_history

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        from ..models.codex_content_item import CodexContentItem
        from ..models.codex_git_info import CodexGitInfo
        from ..models.codex_local_shell_action import (
            CodexLocalShellAction,
        )
        from ..models.codex_payload_arguments_type_1 import (
            CodexPayloadArgumentsType1,
        )
        from ..models.codex_payload_input_type_1 import (
            CodexPayloadInputType1,
        )
        from ..models.codex_reasoning_summary_item import (
            CodexReasoningSummaryItem,
        )

        d = dict(src_dict)

        def _parse_type_(data: object) -> CodexPayloadTypeType0 | None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                type_type_0 = CodexPayloadTypeType0(data)

                return type_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(CodexPayloadTypeType0 | None | str | Unset, data)

        type_ = _parse_type_(d.pop("type", UNSET))

        def _parse_role(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        role = _parse_role(d.pop("role", UNSET))

        def _parse_content(data: object) -> list[CodexContentItem] | None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                content_type_0 = []
                _content_type_0 = data
                for content_type_0_item_data in _content_type_0:
                    content_type_0_item = CodexContentItem.from_dict(
                        content_type_0_item_data
                    )

                    content_type_0.append(content_type_0_item)

                return content_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(list[CodexContentItem] | None | str | Unset, data)

        content = _parse_content(d.pop("content", UNSET))

        def _parse_summary(
            data: object,
        ) -> list[CodexReasoningSummaryItem] | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                summary_type_0 = []
                _summary_type_0 = data
                for summary_type_0_item_data in _summary_type_0:
                    summary_type_0_item = CodexReasoningSummaryItem.from_dict(
                        summary_type_0_item_data
                    )

                    summary_type_0.append(summary_type_0_item)

                return summary_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(list[CodexReasoningSummaryItem] | None | Unset, data)

        summary = _parse_summary(d.pop("summary", UNSET))

        def _parse_encrypted_content(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        encrypted_content = _parse_encrypted_content(d.pop("encrypted_content", UNSET))

        def _parse_name(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        name = _parse_name(d.pop("name", UNSET))

        def _parse_namespace(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        namespace = _parse_namespace(d.pop("namespace", UNSET))

        def _parse_call_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        call_id = _parse_call_id(d.pop("call_id", UNSET))

        def _parse_arguments(
            data: object,
        ) -> CodexPayloadArgumentsType1 | None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                arguments_type_1 = CodexPayloadArgumentsType1.from_dict(data)

                return arguments_type_1
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(CodexPayloadArgumentsType1 | None | str | Unset, data)

        arguments = _parse_arguments(d.pop("arguments", UNSET))

        def _parse_output(data: object) -> list[CodexContentItem] | None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                output_type_1 = []
                _output_type_1 = data
                for output_type_1_item_data in _output_type_1:
                    output_type_1_item = CodexContentItem.from_dict(
                        output_type_1_item_data
                    )

                    output_type_1.append(output_type_1_item)

                return output_type_1
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(list[CodexContentItem] | None | str | Unset, data)

        output = _parse_output(d.pop("output", UNSET))

        def _parse_action(data: object) -> CodexLocalShellAction | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                action_type_0 = CodexLocalShellAction.from_dict(data)

                return action_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(CodexLocalShellAction | None | Unset, data)

        action = _parse_action(d.pop("action", UNSET))

        def _parse_input_(data: object) -> CodexPayloadInputType1 | None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                input_type_1 = CodexPayloadInputType1.from_dict(data)

                return input_type_1
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(CodexPayloadInputType1 | None | str | Unset, data)

        input_ = _parse_input_(d.pop("input", UNSET))

        def _parse_model(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        model = _parse_model(d.pop("model", UNSET))

        def _parse_user_instructions(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        user_instructions = _parse_user_instructions(d.pop("user_instructions", UNSET))

        def _parse_developer_instructions(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        developer_instructions = _parse_developer_instructions(
            d.pop("developer_instructions", UNSET)
        )

        def _parse_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        id = _parse_id(d.pop("id", UNSET))

        def _parse_subagent_history_start_ordinal(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        subagent_history_start_ordinal = _parse_subagent_history_start_ordinal(
            d.pop("subagent_history_start_ordinal", UNSET)
        )

        def _parse_cwd(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        cwd = _parse_cwd(d.pop("cwd", UNSET))

        def _parse_cli_version(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        cli_version = _parse_cli_version(d.pop("cli_version", UNSET))

        def _parse_originator(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        originator = _parse_originator(d.pop("originator", UNSET))

        def _parse_git(data: object) -> CodexGitInfo | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                git_type_0 = CodexGitInfo.from_dict(data)

                return git_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(CodexGitInfo | None | Unset, data)

        git = _parse_git(d.pop("git", UNSET))

        def _parse_message(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        message = _parse_message(d.pop("message", UNSET))

        def _parse_replacement_history(
            data: object,
        ) -> list[CodexPayload] | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                replacement_history_type_0 = []
                _replacement_history_type_0 = data
                for replacement_history_type_0_item_data in _replacement_history_type_0:
                    replacement_history_type_0_item = CodexPayload.from_dict(
                        replacement_history_type_0_item_data
                    )

                    replacement_history_type_0.append(replacement_history_type_0_item)

                return replacement_history_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(list[CodexPayload] | None | Unset, data)

        replacement_history = _parse_replacement_history(
            d.pop("replacement_history", UNSET)
        )

        codex_payload = cls(
            type_=type_,
            role=role,
            content=content,
            summary=summary,
            encrypted_content=encrypted_content,
            name=name,
            namespace=namespace,
            call_id=call_id,
            arguments=arguments,
            output=output,
            action=action,
            input_=input_,
            model=model,
            user_instructions=user_instructions,
            developer_instructions=developer_instructions,
            id=id,
            subagent_history_start_ordinal=subagent_history_start_ordinal,
            cwd=cwd,
            cli_version=cli_version,
            originator=originator,
            git=git,
            message=message,
            replacement_history=replacement_history,
        )

        codex_payload.additional_properties = d
        return codex_payload

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
