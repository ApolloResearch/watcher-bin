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

from ..models.raw_pre_tool_use_hook_request_mode import RawPreToolUseHookRequestMode
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.capture_source import CaptureSource
    from ..models.conversation_identity import ConversationIdentity
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

    ``conversation`` names one authoritative identity selected by the adapter;
    neither caller ``external_ids`` nor parsed native IDs add matching aliases.
    Without it, legacy requests merge caller aliases with parsed harness IDs
    and can reconcile compatible transcript history across complementary aliases. ``source`` describes
    delivery only and never selects identity or permissions. ``user`` is honored
    only for callers allowed to impersonate. The remaining fields have the
    pre-tool-use hook's meaning.

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
            conversation (ConversationIdentity | None | Unset): One authoritative conversation identity. When supplied,
                neither external_ids nor native body metadata add matching aliases. Does not grant access. A recognized harness
                takes precedence; otherwise a native namespace selects the harness and its grading rules.
            parent_conversation (ConversationIdentity | None | Unset): Optional immediate parent, requiring a distinct
                conversation in the same namespace. Watcher links after recording; the parent may initially have no messages.
                Link failures preserve the capture and retry when later captures include the parent identity. Existing ingestion
                permissions apply; this adds no matching aliases.
            spawning_tool_use_id (None | str | Unset): Optional native call ID that spawned this child, requiring
                parent_conversation. Watcher resolves it against the parent's stored messages. Missing messages leave the call
                ID stored with no message link; later child captures carrying parent identity retry resolution.
            source (CaptureSource | None | Unset): Delivery integration: type gateway, sdk or other, with an optional stable
                integration name. Raw captures cannot use client. The resolved type is shared by session and decision recording;
                the name is reporting metadata. Neither selects a conversation or grants permissions. Accepted captures retain
                this source even when all messages already exist.
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
            withheld_tool_use_ids (list[str] | None | Unset): Optional. Tool-use IDs of the calls a gateway withheld from
                the client in favor of the response this request records: the refused calls and the calls withheld with them in
                the same proposal, never a call delivered to the client. Omit it when nothing was withheld. The recorded
                response is response_body's message, or the last request message when that is empty. Watcher shows each named
                call that it evaluated in the same session before this response. A call still pending or unknown gets execution
                status blocked if Watcher refused it and cancelled otherwise; unknown IDs are ignored, and so is the field on
                ephemeral requests. A non-empty list requires withholds_refused_calls to be true. At most 4,096 IDs; duplicates
                are removed. Older servers reject the field with HTTP 422.
            withholds_refused_calls (bool | Unset): Optional. True when the caller withholds from the client every call
                Watcher denies or escalates in enforce mode, so Watcher records such a refusal's execution status as blocked
                when it decides it. Leave it false when the reply may already have reached the client, as on an observation
                path. Older servers reject the field with HTTP 422. Default: False.
    """

    format_: Literal["raw"]
    request_body: RawPreToolUseHookRequestRequestBody
    response_body: RawPreToolUseHookRequestResponseBody
    url: str | Unset = ""
    provider: None | str | Unset = UNSET
    user_agent: None | str | Unset = UNSET
    conversation: ConversationIdentity | None | Unset = UNSET
    parent_conversation: ConversationIdentity | None | Unset = UNSET
    spawning_tool_use_id: None | str | Unset = UNSET
    source: CaptureSource | None | Unset = UNSET
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
    withheld_tool_use_ids: list[str] | None | Unset = UNSET
    withholds_refused_calls: bool | Unset = False

    def to_dict(self) -> dict[str, Any]:
        from ..models.capture_source import CaptureSource
        from ..models.conversation_identity import ConversationIdentity
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

        conversation: dict[str, Any] | None | Unset
        if isinstance(self.conversation, Unset):
            conversation = UNSET
        elif isinstance(self.conversation, ConversationIdentity):
            conversation = self.conversation.to_dict()
        else:
            conversation = self.conversation

        parent_conversation: dict[str, Any] | None | Unset
        if isinstance(self.parent_conversation, Unset):
            parent_conversation = UNSET
        elif isinstance(self.parent_conversation, ConversationIdentity):
            parent_conversation = self.parent_conversation.to_dict()
        else:
            parent_conversation = self.parent_conversation

        spawning_tool_use_id: None | str | Unset
        if isinstance(self.spawning_tool_use_id, Unset):
            spawning_tool_use_id = UNSET
        else:
            spawning_tool_use_id = self.spawning_tool_use_id

        source: dict[str, Any] | None | Unset
        if isinstance(self.source, Unset):
            source = UNSET
        elif isinstance(self.source, CaptureSource):
            source = self.source.to_dict()
        else:
            source = self.source

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

        withheld_tool_use_ids: list[str] | None | Unset
        if isinstance(self.withheld_tool_use_ids, Unset):
            withheld_tool_use_ids = UNSET
        elif isinstance(self.withheld_tool_use_ids, list):
            withheld_tool_use_ids = self.withheld_tool_use_ids

        else:
            withheld_tool_use_ids = self.withheld_tool_use_ids

        withholds_refused_calls = self.withholds_refused_calls

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
        if conversation is not UNSET:
            field_dict["conversation"] = conversation
        if parent_conversation is not UNSET:
            field_dict["parent_conversation"] = parent_conversation
        if spawning_tool_use_id is not UNSET:
            field_dict["spawning_tool_use_id"] = spawning_tool_use_id
        if source is not UNSET:
            field_dict["source"] = source
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
        if withheld_tool_use_ids is not UNSET:
            field_dict["withheld_tool_use_ids"] = withheld_tool_use_ids
        if withholds_refused_calls is not UNSET:
            field_dict["withholds_refused_calls"] = withholds_refused_calls

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        from ..models.capture_source import CaptureSource
        from ..models.conversation_identity import ConversationIdentity
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

        def _parse_conversation(data: object) -> ConversationIdentity | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                conversation_type_0 = ConversationIdentity.from_dict(data)

                return conversation_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(ConversationIdentity | None | Unset, data)

        conversation = _parse_conversation(d.pop("conversation", UNSET))

        def _parse_parent_conversation(
            data: object,
        ) -> ConversationIdentity | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                parent_conversation_type_0 = ConversationIdentity.from_dict(data)

                return parent_conversation_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(ConversationIdentity | None | Unset, data)

        parent_conversation = _parse_parent_conversation(
            d.pop("parent_conversation", UNSET)
        )

        def _parse_spawning_tool_use_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        spawning_tool_use_id = _parse_spawning_tool_use_id(
            d.pop("spawning_tool_use_id", UNSET)
        )

        def _parse_source(data: object) -> CaptureSource | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                source_type_0 = CaptureSource.from_dict(data)

                return source_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(CaptureSource | None | Unset, data)

        source = _parse_source(d.pop("source", UNSET))

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

        def _parse_withheld_tool_use_ids(data: object) -> list[str] | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                withheld_tool_use_ids_type_0 = cast(list[str], data)

                return withheld_tool_use_ids_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(list[str] | None | Unset, data)

        withheld_tool_use_ids = _parse_withheld_tool_use_ids(
            d.pop("withheld_tool_use_ids", UNSET)
        )

        withholds_refused_calls = d.pop("withholds_refused_calls", UNSET)

        raw_pre_tool_use_hook_request = cls(
            format_=format_,
            request_body=request_body,
            response_body=response_body,
            url=url,
            provider=provider,
            user_agent=user_agent,
            conversation=conversation,
            parent_conversation=parent_conversation,
            spawning_tool_use_id=spawning_tool_use_id,
            source=source,
            response_index=response_index,
            external_ids=external_ids,
            user=user,
            mode=mode,
            ephemeral=ephemeral,
            force_regrade=force_regrade,
            skip_rules=skip_rules,
            policy_version=policy_version,
            settings_overrides=settings_overrides,
            withheld_tool_use_ids=withheld_tool_use_ids,
            withholds_refused_calls=withholds_refused_calls,
        )

        return raw_pre_tool_use_hook_request
