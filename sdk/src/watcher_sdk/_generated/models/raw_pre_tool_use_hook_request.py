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

from ..models.raw_pre_tool_use_hook_request_mode import RawPreToolUseHookRequestMode
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.raw_pre_tool_use_hook_request_external_ids_type_0 import (
        RawPreToolUseHookRequestExternalIdsType0,
    )
    from ..models.raw_pre_tool_use_hook_request_request_body import (
        RawPreToolUseHookRequestRequestBody,
    )
    from ..models.raw_pre_tool_use_hook_request_response_body import (
        RawPreToolUseHookRequestResponseBody,
    )
    from ..models.raw_pre_tool_use_hook_request_settings_overrides_type_1 import (
        RawPreToolUseHookRequestSettingsOverridesType1,
    )


T = TypeVar("T", bound="RawPreToolUseHookRequest")


@_attrs_define
class RawPreToolUseHookRequest:
    """A pre-tool-use hook request carrying one provider request and its complete response.

    ``request_body`` is the JSON the client sent to the gateway and
    ``response_body`` the assembled JSON response the gateway would return,
    both in the same wire format: OpenAI Chat Completions or Responses,
    Anthropic Messages, Gemini generateContent or Bedrock Converse. Streams must
    be assembled into the equivalent non-streaming body first. ``url`` is the
    client-facing endpoint path or URL; it breaks ties between formats and is
    recorded without credentials, query or fragment.

    ``external_ids`` carries the gateway's own conversation ID, typically under
    ``other``. A recognized harness's native ID is added to it; the caller
    cannot replace a native ID the harness supplied. With neither, the session
    is found by transcript prefix. ``user`` is honored only for callers allowed
    to impersonate. The remaining fields have the pre-tool-use hook's meaning.

    The response is a list with one output per selected new client call, in
    response order. Each ``tool_use_id`` is the provider's own call ID, except
    for Gemini, whose calls get stable generated IDs and are matched by order
    within the selected candidate. Only the selected choice or candidate may
    be delivered. The gateway must match every executable client call it will
    deliver to exactly one output before applying its decision. Withhold the
    response if a call has no output, IDs are duplicated, or an output cannot
    be matched to a call. Gemini requires equal call and output counts.

    Anthropic calls before the final ``fallback`` block have no output. An
    empty list means no client calls were selected, not that the original
    response contains none. There is no limit on the number of tool calls in
    one response (the watcher format accepts at most 32 inputs), because a
    gateway does not control how many calls a provider returns.

        Attributes:
            format_ (Literal['raw']):
            request_body (RawPreToolUseHookRequestRequestBody):
            response_body (RawPreToolUseHookRequestResponseBody):
            url (str | Unset): Client-facing endpoint path or URL, e.g. /v1/chat/completions. Default: ''.
            provider (None | str | Unset): Gateway route or model alias, recorded as provenance.
            user_agent (None | str | Unset): The client's User-Agent header, used to recognize harnesses.
            response_index (int | None | Unset): Zero-based array position of the Chat choice or Gemini candidate; required
                for multiple alternatives.
            external_ids (None | RawPreToolUseHookRequestExternalIdsType0 | Unset):
            user (None | str | Unset):
            mode (RawPreToolUseHookRequestMode | Unset):  Default: RawPreToolUseHookRequestMode.FULL.
            ephemeral (bool | Unset):  Default: False.
            force_regrade (bool | Unset):  Default: False.
            skip_rules (bool | Unset):  Default: False.
            policy_version (None | str | Unset):
            settings_overrides (None | RawPreToolUseHookRequestSettingsOverridesType1 | str | Unset):
    """

    format_: Literal["raw"]
    request_body: RawPreToolUseHookRequestRequestBody
    response_body: RawPreToolUseHookRequestResponseBody
    url: str | Unset = ""
    provider: None | str | Unset = UNSET
    user_agent: None | str | Unset = UNSET
    response_index: int | None | Unset = UNSET
    external_ids: None | RawPreToolUseHookRequestExternalIdsType0 | Unset = UNSET
    user: None | str | Unset = UNSET
    mode: RawPreToolUseHookRequestMode | Unset = RawPreToolUseHookRequestMode.FULL
    ephemeral: bool | Unset = False
    force_regrade: bool | Unset = False
    skip_rules: bool | Unset = False
    policy_version: None | str | Unset = UNSET
    settings_overrides: (
        None | RawPreToolUseHookRequestSettingsOverridesType1 | str | Unset
    ) = UNSET

    def to_dict(self) -> dict[str, Any]:
        from ..models.raw_pre_tool_use_hook_request_external_ids_type_0 import (
            RawPreToolUseHookRequestExternalIdsType0,
        )
        from ..models.raw_pre_tool_use_hook_request_settings_overrides_type_1 import (
            RawPreToolUseHookRequestSettingsOverridesType1,
        )

        format_ = self.format_

        request_body = self.request_body.to_dict()

        response_body = self.response_body.to_dict()

        url = self.url

        provider: None | str | Unset
        if isinstance(self.provider, Unset):
            provider = UNSET
        else:
            provider = self.provider

        user_agent: None | str | Unset
        if isinstance(self.user_agent, Unset):
            user_agent = UNSET
        else:
            user_agent = self.user_agent

        response_index: int | None | Unset
        if isinstance(self.response_index, Unset):
            response_index = UNSET
        else:
            response_index = self.response_index

        external_ids: dict[str, Any] | None | Unset
        if isinstance(self.external_ids, Unset):
            external_ids = UNSET
        elif isinstance(self.external_ids, RawPreToolUseHookRequestExternalIdsType0):
            external_ids = self.external_ids.to_dict()
        else:
            external_ids = self.external_ids

        user: None | str | Unset
        if isinstance(self.user, Unset):
            user = UNSET
        else:
            user = self.user

        mode: str | Unset = UNSET
        if not isinstance(self.mode, Unset):
            mode = self.mode.value

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
            self.settings_overrides, RawPreToolUseHookRequestSettingsOverridesType1
        ):
            settings_overrides = self.settings_overrides.to_dict()
        else:
            settings_overrides = self.settings_overrides

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "format": format_,
                "request_body": request_body,
                "response_body": response_body,
            }
        )
        if url is not UNSET:
            field_dict["url"] = url
        if provider is not UNSET:
            field_dict["provider"] = provider
        if user_agent is not UNSET:
            field_dict["user_agent"] = user_agent
        if response_index is not UNSET:
            field_dict["response_index"] = response_index
        if external_ids is not UNSET:
            field_dict["external_ids"] = external_ids
        if user is not UNSET:
            field_dict["user"] = user
        if mode is not UNSET:
            field_dict["mode"] = mode
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
        from ..models.raw_pre_tool_use_hook_request_external_ids_type_0 import (
            RawPreToolUseHookRequestExternalIdsType0,
        )
        from ..models.raw_pre_tool_use_hook_request_request_body import (
            RawPreToolUseHookRequestRequestBody,
        )
        from ..models.raw_pre_tool_use_hook_request_response_body import (
            RawPreToolUseHookRequestResponseBody,
        )
        from ..models.raw_pre_tool_use_hook_request_settings_overrides_type_1 import (
            RawPreToolUseHookRequestSettingsOverridesType1,
        )

        d = dict(src_dict)
        format_ = cast(Literal["raw"], d.pop("format"))
        if format_ != "raw":
            raise ValueError(f"format must match const 'raw', got '{format_}'")

        request_body = RawPreToolUseHookRequestRequestBody.from_dict(
            d.pop("request_body")
        )

        response_body = RawPreToolUseHookRequestResponseBody.from_dict(
            d.pop("response_body")
        )

        url = d.pop("url", UNSET)

        def _parse_provider(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        provider = _parse_provider(d.pop("provider", UNSET))

        def _parse_user_agent(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        user_agent = _parse_user_agent(d.pop("user_agent", UNSET))

        def _parse_response_index(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        response_index = _parse_response_index(d.pop("response_index", UNSET))

        def _parse_external_ids(
            data: object,
        ) -> None | RawPreToolUseHookRequestExternalIdsType0 | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                external_ids_type_0 = (
                    RawPreToolUseHookRequestExternalIdsType0.from_dict(data)
                )

                return external_ids_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | RawPreToolUseHookRequestExternalIdsType0 | Unset, data)

        external_ids = _parse_external_ids(d.pop("external_ids", UNSET))

        def _parse_user(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        user = _parse_user(d.pop("user", UNSET))

        _mode = d.pop("mode", UNSET)
        mode: RawPreToolUseHookRequestMode | Unset
        if isinstance(_mode, Unset):
            mode = UNSET
        else:
            mode = RawPreToolUseHookRequestMode(_mode)

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
        ) -> None | RawPreToolUseHookRequestSettingsOverridesType1 | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                settings_overrides_type_1 = (
                    RawPreToolUseHookRequestSettingsOverridesType1.from_dict(data)
                )

                return settings_overrides_type_1
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(
                None | RawPreToolUseHookRequestSettingsOverridesType1 | str | Unset,
                data,
            )

        settings_overrides = _parse_settings_overrides(
            d.pop("settings_overrides", UNSET)
        )

        raw_pre_tool_use_hook_request = cls(
            format_=format_,
            request_body=request_body,
            response_body=response_body,
            url=url,
            provider=provider,
            user_agent=user_agent,
            response_index=response_index,
            external_ids=external_ids,
            user=user,
            mode=mode,
            ephemeral=ephemeral,
            force_regrade=force_regrade,
            skip_rules=skip_rules,
            policy_version=policy_version,
            settings_overrides=settings_overrides,
        )

        return raw_pre_tool_use_hook_request
