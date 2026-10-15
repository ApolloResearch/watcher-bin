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
from typing_extensions import Self

from ..models.codex_hook_request_mode import CodexHookRequestMode
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.codex_hook_request_external_ids_type_0 import (
        CodexHookRequestExternalIdsType0,
    )
    from ..models.codex_hook_request_settings_overrides_type_1 import (
        CodexHookRequestSettingsOverridesType1,
    )
    from ..models.codex_trajectory import CodexTrajectory
    from ..models.hook_append_anchor import HookAppendAnchor
    from ..models.monitoring_input import MonitoringInput


T = TypeVar("T", bound="CodexHookRequest")


@_attrs_define
class CodexHookRequest:
    """Judge pending calls with a Codex rollout as their context.

    ``messages`` holds the rollout's entries, or only those after
    ``append_after``. Codex's hooks report a shell call as ``Bash`` and leave
    out how it runs (its working directory, sandbox escalation), so each
    selected call must name its ``tool_use_id`` (the rollout's ``call_id``),
    and the rollout's record of that call supplies those details. A call
    without an ID, or one the rollout does not hold, is never allowed
    automatically.

        Attributes:
            format_ (Literal['codex-jsonl']):
            messages (CodexTrajectory): A trajectory in Codex JSONL format (raw events from the session rollout file).
            append_after (HookAppendAnchor | None | Unset): Append messages after this exact stored session/trajectory
                anchor. The server loads its prefix before validating or grading calls. Requires session-write authority and
                cannot be combined with ephemeral. Successful append responses return the committed next anchor and ordered
                results. Retry once with the full transcript and without append_after on 404, 409, or 422.
            input_ (list[MonitoringInput] | MonitoringInput | None | Unset):
            mode (CodexHookRequestMode | Unset):  Default: CodexHookRequestMode.FULL.
            external_ids (CodexHookRequestExternalIdsType0 | None | Unset): Distinct conversation IDs from the harness and
                gateway, keyed by source. Required unless ephemeral is true; send every id you have, e.g. {"claude_code":
                "<Claude Code session uuid>", "other": "<your own conversation id>"}. The keys also name the harness. A caller
                with no id at all records id-less by sending an explicit null value, e.g. {"other": null} or {"claude_code":
                null}: the session is then found by transcript prefix. With append_after the explicit anchor selects the
                session; any non-null external IDs must already belong to that session.
            user (None | str | Unset):
            ephemeral (bool | Unset):  Default: False.
            force_regrade (bool | Unset): Evaluate again even when this session and tool-use ID have a completed judgment.
                The new result may replace the recorded decision, including in observe mode. Otherwise a readable completed
                judgment with matching tool arguments is reused, regardless of policy version, under the current enforcement
                posture. Default: False.
            skip_rules (bool | Unset):  Default: False.
            policy_version (None | str | Unset):
            settings_overrides (CodexHookRequestSettingsOverridesType1 | None | str | Unset): Per-request settings as YAML
                or a JSON object; at most 65,536 characters of YAML or serialized JSON. Administrator permission locks apply.
    """

    format_: Literal["codex-jsonl"]
    messages: CodexTrajectory
    append_after: HookAppendAnchor | None | Unset = UNSET
    input_: list[MonitoringInput] | MonitoringInput | None | Unset = UNSET
    mode: CodexHookRequestMode | Unset = CodexHookRequestMode.FULL
    external_ids: CodexHookRequestExternalIdsType0 | None | Unset = UNSET
    user: None | str | Unset = UNSET
    ephemeral: bool | Unset = False
    force_regrade: bool | Unset = False
    skip_rules: bool | Unset = False
    policy_version: None | str | Unset = UNSET
    settings_overrides: CodexHookRequestSettingsOverridesType1 | None | str | Unset = (
        UNSET
    )

    def to_dict(self) -> dict[str, Any]:
        from ..models.codex_hook_request_external_ids_type_0 import (
            CodexHookRequestExternalIdsType0,
        )
        from ..models.codex_hook_request_settings_overrides_type_1 import (
            CodexHookRequestSettingsOverridesType1,
        )
        from ..models.hook_append_anchor import HookAppendAnchor
        from ..models.monitoring_input import MonitoringInput

        format_ = self.format_

        messages = self.messages.to_dict()

        append_after: dict[str, Any] | None | Unset
        if isinstance(self.append_after, Unset):
            append_after = UNSET
        elif isinstance(self.append_after, HookAppendAnchor):
            append_after = self.append_after.to_dict()
        else:
            append_after = self.append_after

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

        mode: str | Unset = UNSET
        if not isinstance(self.mode, Unset):
            mode = self.mode.value

        external_ids: dict[str, Any] | None | Unset
        if isinstance(self.external_ids, Unset):
            external_ids = UNSET
        elif isinstance(self.external_ids, CodexHookRequestExternalIdsType0):
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
            self.settings_overrides, CodexHookRequestSettingsOverridesType1
        ):
            settings_overrides = self.settings_overrides.to_dict()
        else:
            settings_overrides = self.settings_overrides

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "format": format_,
                "messages": messages,
            }
        )
        if append_after is not UNSET:
            field_dict["append_after"] = append_after
        if input_ is not UNSET:
            field_dict["input"] = input_
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
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        from ..models.codex_hook_request_external_ids_type_0 import (
            CodexHookRequestExternalIdsType0,
        )
        from ..models.codex_hook_request_settings_overrides_type_1 import (
            CodexHookRequestSettingsOverridesType1,
        )
        from ..models.codex_trajectory import CodexTrajectory
        from ..models.hook_append_anchor import HookAppendAnchor
        from ..models.monitoring_input import MonitoringInput

        d = dict(src_dict)
        format_ = cast(Literal["codex-jsonl"], d.pop("format"))
        if format_ != "codex-jsonl":
            raise ValueError(f"format must match const 'codex-jsonl', got '{format_}'")

        messages = CodexTrajectory.from_dict(d.pop("messages"))

        def _parse_append_after(data: object) -> HookAppendAnchor | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                append_after_type_0 = HookAppendAnchor.from_dict(data)

                return append_after_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(HookAppendAnchor | None | Unset, data)

        append_after = _parse_append_after(d.pop("append_after", UNSET))

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

        _mode = d.pop("mode", UNSET)
        mode: CodexHookRequestMode | Unset
        if isinstance(_mode, Unset):
            mode = UNSET
        else:
            mode = CodexHookRequestMode(_mode)

        def _parse_external_ids(
            data: object,
        ) -> CodexHookRequestExternalIdsType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                external_ids_type_0 = CodexHookRequestExternalIdsType0.from_dict(data)

                return external_ids_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(CodexHookRequestExternalIdsType0 | None | Unset, data)

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
        ) -> CodexHookRequestSettingsOverridesType1 | None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                settings_overrides_type_1 = (
                    CodexHookRequestSettingsOverridesType1.from_dict(data)
                )

                return settings_overrides_type_1
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(
                CodexHookRequestSettingsOverridesType1 | None | str | Unset, data
            )

        settings_overrides = _parse_settings_overrides(
            d.pop("settings_overrides", UNSET)
        )

        codex_hook_request = cls(
            format_=format_,
            messages=messages,
            append_after=append_after,
            input_=input_,
            mode=mode,
            external_ids=external_ids,
            user=user,
            ephemeral=ephemeral,
            force_regrade=force_regrade,
            skip_rules=skip_rules,
            policy_version=policy_version,
            settings_overrides=settings_overrides,
        )

        return codex_hook_request
