from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from typing_extensions import Self

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.codex_local_shell_action_env_type_0 import (
        CodexLocalShellActionEnvType0,
    )


T = TypeVar("T", bound="CodexLocalShellAction")


@_attrs_define
class CodexLocalShellAction:
    """Action body for a ``local_shell_call``. ``command`` is a list of argv strings, not one string.

    Attributes:
        type_ (None | str | Unset):
        command (list[str] | None | Unset):
        timeout_ms (int | None | Unset):
        working_directory (None | str | Unset):
        env (CodexLocalShellActionEnvType0 | None | Unset):
        user (None | str | Unset):
    """

    type_: None | str | Unset = UNSET
    command: list[str] | None | Unset = UNSET
    timeout_ms: int | None | Unset = UNSET
    working_directory: None | str | Unset = UNSET
    env: CodexLocalShellActionEnvType0 | None | Unset = UNSET
    user: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.codex_local_shell_action_env_type_0 import (
            CodexLocalShellActionEnvType0,
        )

        type_: None | str | Unset
        if isinstance(self.type_, Unset):
            type_ = UNSET
        else:
            type_ = self.type_

        command: list[str] | None | Unset
        if isinstance(self.command, Unset):
            command = UNSET
        elif isinstance(self.command, list):
            command = self.command

        else:
            command = self.command

        timeout_ms: int | None | Unset
        if isinstance(self.timeout_ms, Unset):
            timeout_ms = UNSET
        else:
            timeout_ms = self.timeout_ms

        working_directory: None | str | Unset
        if isinstance(self.working_directory, Unset):
            working_directory = UNSET
        else:
            working_directory = self.working_directory

        env: dict[str, Any] | None | Unset
        if isinstance(self.env, Unset):
            env = UNSET
        elif isinstance(self.env, CodexLocalShellActionEnvType0):
            env = self.env.to_dict()
        else:
            env = self.env

        user: None | str | Unset
        if isinstance(self.user, Unset):
            user = UNSET
        else:
            user = self.user

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if type_ is not UNSET:
            field_dict["type"] = type_
        if command is not UNSET:
            field_dict["command"] = command
        if timeout_ms is not UNSET:
            field_dict["timeout_ms"] = timeout_ms
        if working_directory is not UNSET:
            field_dict["working_directory"] = working_directory
        if env is not UNSET:
            field_dict["env"] = env
        if user is not UNSET:
            field_dict["user"] = user

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        from ..models.codex_local_shell_action_env_type_0 import (
            CodexLocalShellActionEnvType0,
        )

        d = dict(src_dict)

        def _parse_type_(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        type_ = _parse_type_(d.pop("type", UNSET))

        def _parse_command(data: object) -> list[str] | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                command_type_0 = cast(list[str], data)

                return command_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(list[str] | None | Unset, data)

        command = _parse_command(d.pop("command", UNSET))

        def _parse_timeout_ms(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        timeout_ms = _parse_timeout_ms(d.pop("timeout_ms", UNSET))

        def _parse_working_directory(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        working_directory = _parse_working_directory(d.pop("working_directory", UNSET))

        def _parse_env(data: object) -> CodexLocalShellActionEnvType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                env_type_0 = CodexLocalShellActionEnvType0.from_dict(data)

                return env_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(CodexLocalShellActionEnvType0 | None | Unset, data)

        env = _parse_env(d.pop("env", UNSET))

        def _parse_user(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        user = _parse_user(d.pop("user", UNSET))

        codex_local_shell_action = cls(
            type_=type_,
            command=command,
            timeout_ms=timeout_ms,
            working_directory=working_directory,
            env=env,
            user=user,
        )

        codex_local_shell_action.additional_properties = d
        return codex_local_shell_action

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
