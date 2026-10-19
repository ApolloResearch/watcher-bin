"""Async Watcher SDK client — the primary user-facing interface.

Wraps the auto-generated httpx client with:
- Typed error hierarchy (maps HTTP status codes to specific exceptions)
- Retry with exponential backoff for transient failures
- Convenience methods (ingest_and_grade)
- Pagination iterators
"""

from __future__ import annotations

import functools
import json as _json
import time
from collections.abc import AsyncIterator, Callable, Coroutine, Mapping, Sequence
from datetime import datetime
from importlib.metadata import version
from typing import Any, Self, TypeVar, overload
from uuid import UUID

import httpx
from pydantic import BaseModel, ConfigDict
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential_jitter
from yaml import YAMLError

import watcher_sdk._generated as _generated
import watcher_sdk._generated.api.auth.auth_callback_v1_auth_callback_post as _auth_callback_api
import watcher_sdk._generated.api.auth.auth_client_config_v1_auth_client_config_get as _auth_client_config_api
import watcher_sdk._generated.api.auth.auth_device_authorize_v1_auth_device_authorize_post as _auth_device_authorize_api
import watcher_sdk._generated.api.auth.auth_device_token_v1_auth_device_token_post as _auth_device_token_api
import watcher_sdk._generated.api.auth.auth_logout_v1_auth_logout_post as _auth_logout_api
import watcher_sdk._generated.api.auth.auth_me_v1_auth_me_get as _auth_me_api
import watcher_sdk._generated.api.auth.auth_refresh_v1_auth_refresh_post as _auth_refresh_api
import watcher_sdk._generated.api.auth.check_permissions_v1_auth_check_permissions_post as _check_permissions_api
import watcher_sdk._generated.api.grade.grade_v1_grade_post as _grade_api
import watcher_sdk._generated.api.graders.create_grader_endpoint_v1_graders_post as _create_grader_api
import watcher_sdk._generated.api.graders.delete_grader_endpoint_v1_graders_grader_id_delete as _delete_grader_api
import watcher_sdk._generated.api.graders.get_grader_endpoint_v1_graders_grader_id_get as _get_grader_api
import watcher_sdk._generated.api.graders.get_grader_version_endpoint_v1_graders_grader_id_version_get as _get_grader_version_api
import watcher_sdk._generated.api.graders.list_grader_models_v1_graders_models_get as _list_grader_models_api
import watcher_sdk._generated.api.graders.list_graders_endpoint_v1_graders_get as _list_graders_api
import watcher_sdk._generated.api.graders.search_graders_endpoint_v1_graders_search_post as _search_graders_api
import watcher_sdk._generated.api.graders.update_grader_endpoint_v1_graders_grader_id_patch as _update_grader_api
import watcher_sdk._generated.api.health.health_v1_health_get as _health_api
import watcher_sdk._generated.api.hooks.aperture_entire_request_hook_v1_hooks_aperture_post as _aperture_entire_request_hook_api
import watcher_sdk._generated.api.hooks.pre_tool_use_hook_v1_hooks_pre_tool_use_post as _pre_tool_use_hook_api
import watcher_sdk._generated.api.ingest.ingest_append_endpoint_v1_sessions_session_id_trajectories_trajectory_hash_append_post as _ingest_append_api
import watcher_sdk._generated.api.ingest.ingest_v1_ingest_post as _ingest_api
import watcher_sdk._generated.api.monitors.get_monitor_customization_v1_monitors_customization_get as _get_monitor_customization_api
import watcher_sdk._generated.api.monitors.grade_by_monitor_v1_monitors_role_grade_post as _grade_by_monitor_api
import watcher_sdk._generated.api.monitors.list_monitors_v1_monitors_get as _list_monitors_api
import watcher_sdk._generated.api.monitors.update_monitor_customization_v1_monitors_customization_put as _update_monitor_customization_api
import watcher_sdk._generated.api.organization.get_org_managed_settings_monitors_v1_organization_managed_settings_path_monitors_get as _get_org_managed_settings_monitors_api
import watcher_sdk._generated.api.organization.get_org_managed_settings_schema_v1_organization_managed_settings_path_schema_get as _get_org_managed_settings_schema_api
import watcher_sdk._generated.api.organization.get_org_managed_settings_v1_organization_managed_settings_path_get as _get_org_managed_settings_api
import watcher_sdk._generated.api.organization.resolve_org_managed_settings_v1_organization_managed_settings_path_resolved_get as _resolve_org_managed_settings_api
import watcher_sdk._generated.api.organization.update_org_managed_settings_v1_organization_managed_settings_path_put as _update_org_managed_settings_api
import watcher_sdk._generated.api.session_content_access_requests.list_session_content_access_requests_v1_session_content_access_requests_get as _list_content_access_requests_api
import watcher_sdk._generated.api.session_content_access_requests.review_session_content_access_request_endpoint_v1_session_content_access_requests_request_id_patch as _review_content_access_request_api
import watcher_sdk._generated.api.session_content_access_requests.revoke_session_content_access_request_endpoint_v1_session_content_access_requests_request_id_revoke_post as _revoke_content_access_request_api
import watcher_sdk._generated.api.sessions.get_current_session_deep_review_v1_sessions_session_id_deep_review_get as _get_current_deep_review_api
import watcher_sdk._generated.api.sessions.get_session_aggregates_endpoint_v1_sessions_aggregates_get as _session_aggregates_api
import watcher_sdk._generated.api.sessions.get_session_deep_review_request_v1_sessions_session_id_deep_review_operation_id_get as _get_deep_review_request_api
import watcher_sdk._generated.api.sessions.get_session_detail_v1_sessions_session_id_get as _get_session_api
import watcher_sdk._generated.api.sessions.get_session_filter_options_endpoint_v1_sessions_filter_options_get as _get_session_filter_options_api
import watcher_sdk._generated.api.sessions.get_session_message_v1_sessions_session_id_messages_message_ref_get as _get_message_api
import watcher_sdk._generated.api.sessions.get_session_tool_call_decision_v1_sessions_session_id_tool_call_decision_get as _get_tool_call_decision_api
import watcher_sdk._generated.api.sessions.get_session_tool_call_v1_sessions_session_id_tool_call_get as _get_tool_call_api
import watcher_sdk._generated.api.sessions.get_session_trajectory_detail_v1_sessions_session_id_trajectories_trajectory_id_get as _get_trajectory_api
import watcher_sdk._generated.api.sessions.list_session_trajectories_v1_sessions_session_id_trajectories_get as _list_trajectories_api
import watcher_sdk._generated.api.sessions.list_sessions_endpoint_v1_sessions_get as _list_sessions_api
import watcher_sdk._generated.api.sessions.request_session_deep_review_v1_sessions_session_id_deep_review_post as _request_deep_review_api
import watcher_sdk._generated.api.sessions.scrub_session_content_v1_sessions_session_id_content_delete as _scrub_session_content_api
import watcher_sdk._generated.api.sessions.search_sessions_endpoint_v1_sessions_search_post as _search_sessions_api
import watcher_sdk._generated.api.tool_call_decisions.upload_tool_call_decisions_batch_v1_tool_call_decisions_batch_post as _tool_call_decisions_api
import watcher_sdk._generated.api.tool_calls.search_tool_calls_endpoint_v1_tool_calls_search_post as _search_tool_calls_api
import watcher_sdk._generated.api.usage.get_grading_usage_endpoint_v1_usage_grading_get as _grading_usage_api
import watcher_sdk._generated.api.usage.get_usage_limits_endpoint_v1_usage_limits_get as _usage_limits_api
import watcher_sdk._generated.api.users.create_my_session_content_access_request_v1_users_me_session_content_access_requests_post as _create_my_content_access_request_api
import watcher_sdk._generated.api.users.get_me_v1_users_me_get as _users_me_api
import watcher_sdk._generated.api.users.get_user_endpoint_v1_users_user_id_get as _get_user_api
import watcher_sdk._generated.api.users.list_my_session_content_access_requests_v1_users_me_session_content_access_requests_get as _list_my_content_access_requests_api
import watcher_sdk._generated.api.users.list_users_endpoint_v1_users_get as _list_users_api
import watcher_sdk._generated.api.version.version_v1_version_get as _version_api
from watcher_sdk._generated.models import (
    ActivatedMonitorsResponse,
    AdminSessionContentAccessRequestListResponse,
    ApertureHookAccepted,
    ApertureHookRequest,
    AuthClientConfig,
    AvailableSessionDetailResponse,
    ChatMessageAssistant,
    ChatMessageSystem,
    ChatMessageTool,
    ChatMessageUser,
    ClaudeCodeHookRequest,
    CodexHookRequest,
    CopilotHookRequest,
    CreateSessionContentAccessRequest,
    DeepReviewRequestResponse,
    DeviceAuthorizationResponse,
    DeviceTokenRequest,
    DeviceTokenResponse,
    GradeByMonitorV1MonitorsRoleGradePostRole,
    GraderDetail,
    GradeRequest,
    GradeResponse,
    GraderListResponse,
    GraderSearchResponse,
    GradingUsageResponse,
    HealthResponse,
    HookAppendResponse,
    HookCallError,
    IngestRequest,
    IngestResponse,
    MessageDetailResponse,
    ModelsConfig,
    MonitorCustomizationResponse,
    MonitoringRequest,
    MonitorsResponse,
    OrgManagedSettingsDoc,
    OrgManagedSettingsResolved,
    OrgManagedSettingsUpdate,
    PermissionCheckRequest,
    PermissionCheckResponse,
    PreToolUseHookRequest,
    PreToolUseHookResponse,
    RawPreToolUseHookRequest,
    ReviewSessionContentAccessRequest,
    ScrubbedSessionDetailResponse,
    SessionAggregatesResponse,
    SessionContentAccessRequestListResponse,
    SessionContentAccessRequestStatus,
    SessionContentAccessRequestSummary,
    SessionContentAccessRequestView,
    SessionDeepReviewResponse,
    SessionFilterOptionsResponse,
    SessionListResponse,
    SessionSummary,
    ToolCallDecisionBatchRequest,
    ToolCallDecisionBatchResponse,
    ToolCallDetailResponse,
    ToolCallFindingsResponse,
    ToolCallListResponse,
    ToolCallSearchFilters,
    ToolCallSearchFiltersDecisionCategoriesType0Item,
    ToolCallSearchFiltersSeveritiesType0Item,
    ToolCallSearchParams,
    ToolCallSearchParamsSortBy,
    ToolCallSearchParamsSortOrder,
    TrajectoryDetailResponse,
    TrajectoryListInSessionResponse,
    TrajectoryView,
    UpdateMonitorCustomizationRequest,
    UsageLimitsResponse,
    UserFilter,
    UserListResponse,
    UserSummary,
    VersionResponse,
)
from watcher_sdk._generated.models.aperture_log import ApertureLog
from watcher_sdk._generated.models.callback_request import CallbackRequest
from watcher_sdk._generated.models.claude_code_trajectory import ClaudeCodeTrajectory
from watcher_sdk._generated.models.codex_trajectory import CodexTrajectory
from watcher_sdk._generated.models.copilot_trajectory import CopilotTrajectory
from watcher_sdk._generated.models.create_grader_request import CreateGraderRequest
from watcher_sdk._generated.models.create_grader_request_reasoning_effort_type_0 import (
    CreateGraderRequestReasoningEffortType0,
)
from watcher_sdk._generated.models.create_grader_request_scores import CreateGraderRequestScores
from watcher_sdk._generated.models.get_grading_usage_endpoint_v1_usage_grading_get_bucket import (
    GetGradingUsageEndpointV1UsageGradingGetBucket,
)
from watcher_sdk._generated.models.get_grading_usage_endpoint_v1_usage_grading_get_kind import (
    GetGradingUsageEndpointV1UsageGradingGetKind,
)
from watcher_sdk._generated.models.get_session_aggregates_endpoint_v1_sessions_aggregates_get_bucket import (
    GetSessionAggregatesEndpointV1SessionsAggregatesGetBucket,
)
from watcher_sdk._generated.models.get_session_aggregates_endpoint_v1_sessions_aggregates_get_severity_threshold import (
    GetSessionAggregatesEndpointV1SessionsAggregatesGetSeverityThreshold,
)
from watcher_sdk._generated.models.grader_search_request import GraderSearchRequest
from watcher_sdk._generated.models.ingest_append_request import IngestAppendRequest
from watcher_sdk._generated.models.refresh_request import RefreshRequest
from watcher_sdk._generated.models.session_search_filters import SessionSearchFilters
from watcher_sdk._generated.models.session_search_filters_external_ids_type_0 import (
    SessionSearchFiltersExternalIdsType0,
)
from watcher_sdk._generated.models.session_search_filters_grading_statuses_type_0_item import (
    SessionSearchFiltersGradingStatusesType0Item,
)
from watcher_sdk._generated.models.session_search_filters_severities_type_0_item import (
    SessionSearchFiltersSeveritiesType0Item,
)
from watcher_sdk._generated.models.session_search_params import SessionSearchParams
from watcher_sdk._generated.models.session_search_params_sort_by import SessionSearchParamsSortBy
from watcher_sdk._generated.models.session_search_params_sort_order import SessionSearchParamsSortOrder
from watcher_sdk._generated.models.token_response import TokenResponse
from watcher_sdk._generated.models.update_grader_request import UpdateGraderRequest
from watcher_sdk._generated.models.user_profile import UserProfile
from watcher_sdk._generated.types import UNSET, Unset
from watcher_sdk._pagination import PaginatedIterator, SearchPaginatedIterator
from watcher_sdk.auth_support import REFRESH_TOKEN_COOKIE_NAME, AuthExchangeResult, AuthLogoutResult
from watcher_sdk.errors import (
    WatcherAPIError,
    WatcherConnectionError,
    WatcherNotFoundError,
    WatcherRateLimitError,
    WatcherTimeoutError,
    raise_for_status,
)
from watcher_sdk.settings_schema.command_rules_eval import (
    TERMINAL_THRESHOLD_LABEL,
    TERMINAL_THRESHOLD_PATTERN,
    CommandRuleMatch,
    RuleAction,
    apply_org_posture,
    command_rules_from_tree,
    evaluate_command_rules,
    resolve_tool_thresholds_from_tree,
    terminal_rule_action,
)
from watcher_sdk.settings_schema.watcher_settings_yaml_helpers import (
    RESERVED_TOOL_THRESHOLD_KEYS,
    get_path_or_none,
    unwrap,
)
from watcher_sdk.settings_schema.watcher_settings_yaml_layers import (
    builtin_settings_digest,
    load_builtin_settings,
    load_settings_yaml,
    merge_local_overrides,
    merge_policy_settings,
)

_HookInputMapping = TypeVar("_HookInputMapping", bound=Mapping[str, Any])

ChatMessage = ChatMessageAssistant | ChatMessageSystem | ChatMessageTool | ChatMessageUser
type SessionDetailResponse = AvailableSessionDetailResponse | ScrubbedSessionDetailResponse

# Per-input timeout budget for the pre-tool-use hook wrapper. The server bounds both
# grading stages (hooks_triage_timeout_seconds, 10s, after which the gateway
# grades, and hooks_gateway_timeout_seconds, 300s, after which the org's
# grading-failure policy answers), so grading can take ~310s plus overhead; the
# client-wide default (30s) would abandon — and still pay for — any normally
# slow full grade. The default request budget conservatively covers each input
# in a batch; callers on tight budgets pass their own
# request timeout or send mode="triage_only".
_HOOK_REQUEST_TIMEOUT_SECONDS = 420.0
# How long a fetched org baseline serves local deterministic evaluation before
# it is re-fetched — the same bounded staleness the server's per-org policy
# cache accepts, so the local stage is never staler than the graded stages.
_HOOK_BASELINE_TTL_SECONDS = 60.0

# Per-pattern search ceiling for local rule evaluation: the command string
# comes from the integrator's own agent, so a catastrophic-backtracking org
# pattern must degrade to grading, not hang the caller's hook. Looser than the
# server's bound — this is one client on its own machine, so a slow search
# costs only that caller, and the headroom keeps legitimate long commands out
# of grading.
_LOCAL_RULE_MATCH_TIMEOUT_SECONDS = 1.0

# Rule-engine verdicts that decide a call locally, mapped onto the hook API's
# judgment vocabulary. escalate_triage is absent by design: it requests
# grading, so it falls through to the server like an unmatched call.
_LOCAL_JUDGMENTS: dict[str, str] = {
    RuleAction.ALLOW: "allow",
    RuleAction.DENY: "deny",
    RuleAction.ESCALATE_HUMAN: "escalate",
}

# `external_ids` keys naming a harness whose own tool names the hook endpoint
# translates onto Claude Code's before its deterministic checks (Codex's
# `exec_command` and GitHub Copilot CLI's `view` are evaluated as `Bash` and
# `Read`, for instance).
_TRANSLATED_HARNESS_KEYS = frozenset({"claude_code", "codex", "github_copilot_cli"})
# The coding agents' own transcript formats `pre_tool_use_hook` accepts in `messages`.
_TRANSCRIPT_FILE_FORMATS = ("claude-code-jsonl", "codex-jsonl", "copilot-events-jsonl")


@functools.cache
def _builtin_tool_names() -> frozenset[str]:
    """The tool names the packaged settings configure, which the hook evaluates as sent."""
    return frozenset(load_builtin_settings("settings.yaml")["tool_thresholds"]) - RESERVED_TOOL_THRESHOLD_KEYS


def _hook_may_translate(external_ids: Mapping[str, str | None] | None, tool_name: str) -> bool:
    """Whether the hook endpoint may evaluate this call under a different tool name than the local stage would.

    The endpoint translates harness-specific tool names (Codex's
    `exec_command`, Claude Cowork's `mcp__workspace__bash`, Copilot's `view`)
    for requests whose `external_ids` name Claude Code, Codex or GitHub Copilot
    CLI. This client carries no
    translation table, so for those requests any name the packaged settings do
    not configure goes to the server rather than being judged locally under a
    name the server would not use.
    """
    if not external_ids or _TRANSLATED_HARNESS_KEYS.isdisjoint(external_ids):
        return False
    return tool_name not in _builtin_tool_names()


def _validate_local_hook_identity(
    input: Mapping[str, Any],
    messages: Sequence[Mapping[str, Any]] | None,
    tool_use_id: str | None,
    *,
    is_ephemeral: bool,
) -> Mapping[str, Any] | None:
    """Return validated call input, or None when server normalization is needed.

    The convenience ID overrides the nested ID. When that ID occurs in the
    structured transcript, every occurrence must match the pending function and
    JSON arguments, with omitted input meaning `{}` and explicit null preserved.
    Dual transcripts that differ apart from message IDs require server validation:
    its message parser may normalize omitted fields and explicit defaults alike.
    A supplied transcript must contain the selected ID unless evaluation is
    explicitly ephemeral. Calls without a selected ID or transcript retain local
    evaluation. Identity mismatches raise ValueError before local evaluation.
    Matching a transcript call normalizes omitted arguments to `{}` in a copy;
    callers must use the returned input for both rules and delegated grading.
    The supplied mapping is never mutated, and explicit null stays distinct.
    """
    nested_messages = input.get("messages")
    if messages is not None and nested_messages is not None:
        shared_content = [{key: value for key, value in message.items() if key != "id"} for message in messages]
        nested_content = [{key: value for key, value in message.items() if key != "id"} for message in nested_messages]
        if _json.dumps(shared_content, sort_keys=True) != _json.dumps(nested_content, sort_keys=True):
            return None
    transcript = messages if messages is not None else nested_messages
    selected_id = tool_use_id if tool_use_id is not None else input.get("tool_use_id")
    if transcript is None or selected_id is None:
        return input
    arguments = _json.dumps(input.get("tool_input", {}), sort_keys=True)
    has_selected_call = False
    for message in transcript:
        if message.get("role") != "assistant":
            continue
        for call in message.get("tool_calls") or []:
            if call.get("id") != selected_id:
                continue
            has_selected_call = True
            # JSON comparison preserves boolean/number/string distinctions that
            # Python equality or argument decoding would erase.
            if input.get("tool_name") != call.get("function") or arguments != _json.dumps(
                call.get("arguments"), sort_keys=True
            ):
                raise ValueError(
                    "'input.tool_name' and 'input.tool_input' must match every transcript tool call "
                    "identified by 'input.tool_use_id'"
                )
    if not has_selected_call and not is_ephemeral:
        raise ValueError("'input.tool_use_id' must be one of the tool-call ids in the shared 'messages'")
    if has_selected_call and "tool_input" not in input:
        return {**input, "tool_input": {}}
    return input


class _HookBaseline(BaseModel):
    """The org baseline the local stage evaluates against, with the token that proves which one."""

    model_config = ConfigDict(frozen=True)

    settings: dict[str, Any]
    version_token: str


class LocalPreToolUseDecision(BaseModel):
    """A deterministic hook decision made in-process, without a server round-trip.

    What `AsyncWatcherClient.pre_tool_use` returns when the org
    baseline's terminal thresholds or command rules decide a call — the same
    shared evaluation the hook endpoint would have run, at zero latency. Field
    names match `PreToolUseHookResponse` where the two overlap
    (`decision`, `judged_decision`, `decision_source`,
    `enforcement_mode`), so handling code can read either result uniformly;
    grading-only fields (scores, summaries, grade provenance) do not exist
    here because no grading ran.

    `decision` is posture-applied exactly as the server would
    (`deferred` under an observe-mode org); `judged_decision` is the raw
    verdict. `rule_label`/`rule_pattern`/`rule_action` carry the
    provenance (the reserved "Tool threshold" label for terminal-threshold
    decisions).
    """

    model_config = ConfigDict(frozen=True)

    decision: str
    judged_decision: str
    decision_source: str
    enforcement_mode: str
    rule_label: str
    rule_pattern: str
    rule_action: str


_HTTPX_DEFAULT_USER_AGENT = f"python-httpx/{httpx.__version__}"


@functools.cache
def watcher_sdk_user_agent() -> str:
    """The User-Agent every SDK request to Xylon carries."""
    return f"watcher-sdk/{version('watcher-sdk')}"


def _sdk_user_agent_to_inject(client: httpx.AsyncClient) -> str | None:
    """The User-Agent to put on requests forwarded through a caller-supplied client.

    httpx pre-populates its own default on every client, so the header is never
    absent and ``setdefault`` is a no-op; comparing against that default is the only
    way to tell a caller's choice from httpx filling it in. An explicit caller choice
    yields None, leaving their header in place.
    """
    if client.headers["User-Agent"] == _HTTPX_DEFAULT_USER_AGENT:
        return watcher_sdk_user_agent()
    return None


def _normalize_relative_url(url: str) -> str:
    return url.lstrip("/")


def _normalize_request_kwargs(kwargs: dict[str, Any]) -> dict[str, Any]:
    updated_kwargs = dict(kwargs)
    updated_kwargs["url"] = _normalize_relative_url(str(updated_kwargs["url"]))
    return updated_kwargs


class _RelativePathAsyncClient:
    """Wrapper that strips leading slashes from request URLs before forwarding.

    The generated SDK sends URLs like ``/v1/sessions`` which httpx treats as
    absolute paths, discarding the base_url path prefix (e.g. ``/api``).
    Stripping the leading slash makes the URL relative so httpx correctly
    joins it with the full base_url.

    ``sdk_user_agent``, when set, is stamped on each request forwarded from here.
    Doing it per request rather than on ``wrapped.headers`` keeps a caller-supplied
    client untouched, so their own unrelated traffic keeps its own User-Agent.
    """

    def __init__(self, wrapped: Any, sdk_user_agent: str | None = None) -> None:
        self._wrapped = wrapped
        self._sdk_user_agent = sdk_user_agent

    def _with_sdk_user_agent(self, kwargs: dict[str, Any]) -> dict[str, Any]:
        if self._sdk_user_agent is None:
            return kwargs
        headers = httpx.Headers(kwargs.get("headers"))
        if "User-Agent" in headers:
            return kwargs
        # httpx lets a per-request header win over the client's default, so this
        # tags our traffic without the client-wide mutation doing so would need.
        headers["User-Agent"] = self._sdk_user_agent
        return {**kwargs, "headers": headers}

    async def request(self, **kwargs: Any) -> Any:
        return await self._wrapped.request(**self._with_sdk_user_agent(_normalize_request_kwargs(kwargs)))

    def stream(self, method: str, url: str, **kwargs: Any) -> Any:
        """Proxy httpx.AsyncClient.stream() with the same URL normalization as request().

        Returns the wrapped client's async context manager directly — httpx.stream is
        decorated with @asynccontextmanager, so it's a sync call that returns an
        AsyncContextManager[Response].
        """
        return self._wrapped.stream(method, _normalize_relative_url(url), **self._with_sdk_user_agent(kwargs))

    async def __aenter__(self) -> Self:
        await self._wrapped.__aenter__()
        return self

    async def __aexit__(self, *args: Any, **kwargs: Any) -> None:
        await self._wrapped.__aexit__(*args, **kwargs)


def _wrap_relative_path_async_client(client: Any, sdk_user_agent: str | None = None) -> Any:
    if isinstance(client, _RelativePathAsyncClient):
        return client
    return _RelativePathAsyncClient(client, sdk_user_agent)


class _RelativePathGeneratedClient(_generated.Client):
    """Preserve base URL path prefixes without patching generated SDK output."""

    def set_async_httpx_client(self, async_client: httpx.AsyncClient) -> _RelativePathGeneratedClient:
        super().set_async_httpx_client(
            _wrap_relative_path_async_client(async_client, _sdk_user_agent_to_inject(async_client))
        )
        return self

    def get_async_httpx_client(self) -> Any:
        async_client = super().get_async_httpx_client()
        wrapped_async_client = _wrap_relative_path_async_client(async_client)
        if wrapped_async_client is not async_client:
            self._async_client = wrapped_async_client
        return wrapped_async_client


def _user_from_token_response(token: TokenResponse) -> dict[str, str | None] | None:
    u = token.user
    if isinstance(u, Unset) or u is None:
        return None
    return {str(k): (None if v is None else str(v)) for k, v in u.to_dict().items()}


def _is_retryable(exc: BaseException) -> bool:
    """Determine if an exception is retryable (transient failure)."""
    if isinstance(exc, WatcherConnectionError | WatcherTimeoutError):
        return True
    if isinstance(exc, WatcherRateLimitError):
        return True
    return isinstance(exc, WatcherAPIError) and exc.status_code in (502, 503, 504)


def _raise_for_response(response: Any) -> None:
    """Check a generated Response for HTTP errors and raise SDK exceptions."""
    _raise_for_http_error(response.status_code.value, response.content, response.headers)


def _raise_for_http_error(status: int, content: bytes, headers: Mapping[str, str]) -> None:
    """Raise the SDK exception for an HTTP error status; return for a success status.

    The body is read leniently, so an error body that is not JSON, or not the
    shape the generated models expect, still yields an exception with the real
    status.
    """
    if status >= 400:
        try:
            parsed: object = _json.loads(content)
        except Exception:
            parsed = content.decode(errors="replace") or "Unknown error"
        body: dict[str, object] = parsed if isinstance(parsed, dict) else {"error": parsed}
        raise_for_status(status, body, headers.get("x-request-id"))


def _sdk_method(
    fn: Callable[..., Coroutine[Any, Any, Any]] | None = None,
    *,
    postprocess: Callable[[Any], Any] | None = None,
) -> Any:
    """Decorator that adds retry, error mapping, and response parsing to SDK methods.

    The decorated method should call a generated ``asyncio_detailed()`` function and
    return its ``Response`` object. The decorator:

    1. Wraps the call with tenacity retry (configured via ``self._make_retry()``)
    2. Catches ``httpx.ConnectError`` / ``TimeoutException`` and maps to SDK errors
    3. Checks ``response.status_code >= 400`` and raises SDK error hierarchy
    4. Returns ``response.parsed`` (the deserialized model)

    Use ``postprocess`` to transform the parsed result before returning (e.g. to map
    a generated response model to an SDK-specific type).
    """

    def decorator(fn: Callable[..., Coroutine[Any, Any, Any]]) -> Callable[..., Coroutine[Any, Any, Any]]:
        @functools.wraps(fn)
        async def wrapper(self: AsyncWatcherClient, *args: Any, **kwargs: Any) -> Any:
            @self._make_retry()
            async def _do() -> Any:
                try:
                    response = await fn(self, *args, **kwargs)
                except httpx.ConnectError as e:
                    raise WatcherConnectionError(str(e)) from e
                except httpx.TimeoutException as e:
                    raise WatcherTimeoutError(str(e)) from e

                _raise_for_response(response)
                result = response.parsed
                return postprocess(result) if postprocess else result

            return await _do()

        return wrapper

    if fn is not None:
        return decorator(fn)
    return decorator


class AsyncWatcherClient:
    """Async client for the Watcher API.

    Provides typed methods for all Watcher endpoints with automatic retry,
    error mapping, and pagination support.

    Usage::

        async with AsyncWatcherClient("http://localhost:8000") as client:
            sessions = await client.list_sessions()
            async for session in client.list_sessions_iter():
                print(session.session_id)
    """

    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        api_key: str | None = None,
        access_token: str | None = None,
        timeout: float = 30.0,
        max_retries: int = 3,
        httpx_client: httpx.AsyncClient | None = None,
        manage_external_httpx_client_lifecycle: bool = True,
    ) -> None:
        """Initialize the async Watcher client.

        Args:
            base_url: Base URL of the Watcher API server.
            api_key: Optional API key for authentication (sent as x-api-key header).
            access_token: Optional JWT access token (sent as Authorization: Bearer header).
                If both api_key and access_token are provided, access_token takes precedence.
            timeout: Request timeout in seconds.
            max_retries: Maximum number of retries for transient failures.
            httpx_client: Optional pre-configured httpx.AsyncClient (e.g. ASGI transport in tests).
            manage_external_httpx_client_lifecycle: When ``httpx_client`` is provided, if True (default)
                the SDK enters/exits the generated client on ``async with``, which tears down that
                httpx instance. Set False only when something else owns the same httpx client (e.g.
                an outer test fixture).
        """
        self._max_retries = max_retries
        self._sdk_manages_httpx_lifecycle = httpx_client is None or manage_external_httpx_client_lifecycle
        # (baseline-or-None, fetched_at monotonic) for pre_tool_use's local
        # deterministic stage; None until the first fetch, and a cached None
        # baseline means "decline local evaluation". See _org_hook_baseline.
        self._hook_baseline_cache: tuple[_HookBaseline | None, float] | None = None

        headers: dict[str, str] = {"User-Agent": watcher_sdk_user_agent()}
        if access_token:
            headers["Authorization"] = f"Bearer {access_token}"
        elif api_key:
            headers["x-api-key"] = api_key

        self._generated_client = _RelativePathGeneratedClient(
            base_url=base_url,
            headers=headers,
            timeout=httpx.Timeout(timeout),
        )

        if httpx_client is not None:
            self._generated_client.set_async_httpx_client(httpx_client)

    def _make_retry(self):
        """Create a tenacity retry decorator configured for this client."""
        return retry(
            retry=retry_if_exception(_is_retryable),
            stop=stop_after_attempt(self._max_retries + 1),
            wait=wait_exponential_jitter(initial=0.5, max=10),
            reraise=True,
        )

    # ---- Auth (Watcher API / WorkOS — refresh only in Set-Cookie) ----

    async def _call_auth_raw(self, kwargs: dict[str, Any]) -> httpx.Response:
        """Make a raw httpx request with retry and error handling for auth endpoints.

        Auth endpoints need access to the raw httpx response (for ``Set-Cookie``
        headers), so they cannot use the generated ``asyncio_detailed`` functions.
        """

        @self._make_retry()
        async def _do() -> httpx.Response:
            try:
                http_client = self._generated_client.get_async_httpx_client()
                response = await http_client.request(**kwargs)
            except httpx.ConnectError as e:
                raise WatcherConnectionError(str(e)) from e
            except httpx.TimeoutException as e:
                raise WatcherTimeoutError(str(e)) from e

            if response.status_code >= 400:
                try:
                    body = response.json()
                except Exception:
                    body = {"error": response.text or "Unknown error"}
                raise_for_status(response.status_code, dict(body), response.headers.get("x-request-id"))

            return response

        return await _do()

    async def auth_callback(self, code: str) -> AuthExchangeResult:
        """Exchange a WorkOS authorization code for access + refresh tokens.

        The refresh token is returned only as an httpOnly ``Set-Cookie``, not in
        the JSON body. This method merges cookie + JSON into :class:`AuthExchangeResult`.
        """
        kwargs = _auth_callback_api._get_kwargs(body=CallbackRequest(code=code))
        response = await self._call_auth_raw(kwargs)

        refresh = response.cookies.get(REFRESH_TOKEN_COOKIE_NAME)
        if not refresh:
            raise WatcherAPIError(
                502,
                "missing_refresh_token_cookie",
                "Server did not set refresh_token cookie",
                response.headers.get("x-request-id"),
            )
        token = TokenResponse.from_dict(response.json())
        return AuthExchangeResult(
            access_token=token.access_token,
            refresh_token=str(refresh),
            user=_user_from_token_response(token),
        )

    async def auth_refresh(
        self,
        *,
        refresh_token: str | None = None,
        organization_id: str | None = None,
    ) -> AuthExchangeResult:
        """Refresh an access token.

        Pass ``refresh_token`` or rely on cookies already on the shared httpx client
        (e.g. after a prior ``auth_callback`` on the same :class:`AsyncWatcherClient`).
        """
        kwargs = _auth_refresh_api._get_kwargs(
            body=RefreshRequest(refresh_token=refresh_token, organization_id=organization_id)
        )
        response = await self._call_auth_raw(kwargs)

        new_refresh = response.cookies.get(REFRESH_TOKEN_COOKIE_NAME)
        if not new_refresh:
            raise WatcherAPIError(
                502,
                "missing_refresh_token_cookie",
                "Server did not set refresh_token cookie",
                response.headers.get("x-request-id"),
            )
        token = TokenResponse.from_dict(response.json())
        return AuthExchangeResult(
            access_token=token.access_token,
            refresh_token=str(new_refresh),
            user=_user_from_token_response(token),
        )

    @_sdk_method(postprocess=lambda r: AuthLogoutResult(status=str(r["status"])))
    async def auth_logout(self) -> AuthLogoutResult:
        """Sign out — revokes the WorkOS session (using JWT ``sid``) and clears the refresh cookie.

        The client must have been created with ``access_token=...`` (Bearer) so the server can
        read the session id from the JWT.
        """
        return await _auth_logout_api.asyncio_detailed(client=self._generated_client)  # pyright: ignore[reportReturnType]  # ty: ignore[invalid-return-type]

    @_sdk_method
    async def auth_client_config(self) -> AuthClientConfig:
        """Return the deployment's public auth configuration (no auth required).

        Lets clients discover the auth mode and, in WorkOS mode, the client id
        to start a sign-in with, from nothing but the server URL.
        """
        return await _auth_client_config_api.asyncio_detailed(client=self._generated_client)  # pyright: ignore[reportReturnType]  # ty: ignore[invalid-return-type]

    @_sdk_method
    async def auth_device_authorize(self) -> DeviceAuthorizationResponse:
        """Start a device-authorization sign-in (RFC 8628) for a headless client (no auth required).

        Show the user ``verification_uri_complete`` (or ``verification_uri`` +
        ``user_code``), then poll :meth:`auth_device_token` with the returned
        ``device_code`` every ``interval`` seconds until the user approves.
        """
        return await _auth_device_authorize_api.asyncio_detailed(client=self._generated_client)  # pyright: ignore[reportReturnType]  # ty: ignore[invalid-return-type]

    @_sdk_method
    async def auth_device_token(self, device_code: str) -> DeviceTokenResponse:
        """Poll the outcome of a device-authorization sign-in (no auth required).

        While the user hasn't approved yet, raises :class:`WatcherAPIError`
        with ``code`` ``authorization_pending`` (keep polling) or
        ``slow_down`` (poll less often); a dead attempt raises with
        ``access_denied`` or ``expired_token``. On success both tokens are in
        the response body.
        """
        return await _auth_device_token_api.asyncio_detailed(  # pyright: ignore[reportReturnType]  # ty: ignore[invalid-return-type]
            client=self._generated_client, body=DeviceTokenRequest(device_code=device_code)
        )

    @_sdk_method
    async def auth_me(self) -> UserProfile:
        """Return the current user profile (requires ``access_token`` on the client)."""
        return await _auth_me_api.asyncio_detailed(client=self._generated_client)  # pyright: ignore[reportReturnType]  # ty: ignore[invalid-return-type]

    @_sdk_method
    async def check_permissions(self, permissions: list[str] | tuple[str, ...]) -> PermissionCheckResponse:
        """Check whether the current credential has every requested permission.

        Unknown and ungranted permission slugs are both returned in ``missing``.

        Args:
            permissions: Permission slugs to evaluate against the credential's
                effective authority.

        Returns:
            Whether every permission is granted and the slugs that are missing.
        """
        return await _check_permissions_api.asyncio_detailed(  # pyright: ignore[reportReturnType]  # ty: ignore[invalid-return-type]
            client=self._generated_client,
            body=PermissionCheckRequest(permissions=list(permissions)),
        )

    # ---- Ingest ----

    @_sdk_method
    async def ingest(
        self,
        source: str,
        trajectories: list[ClaudeCodeTrajectory | CodexTrajectory | CopilotTrajectory | ApertureLog],
    ) -> IngestResponse:
        """Ingest trajectories for storage and deduplication.

        Args:
            source: Identifier for the data source (e.g. pipeline name or tool name).
            trajectories: List of trajectories to ingest. Each can be a
                ClaudeCodeTrajectory (Claude Code JSONL entries), a CodexTrajectory
                (Codex rollout JSONL entries), a CopilotTrajectory (one
                conversation's events from a GitHub Copilot CLI events.jsonl),
                or an ApertureLog (S3 reference).

        Returns:
            IngestResponse containing the session_id and trajectory_ids for the
            ingested data. Duplicate trajectories are deduplicated server-side.
        """
        body = IngestRequest(source=source, trajectories=trajectories)
        return await _ingest_api.asyncio_detailed(client=self._generated_client, body=body)  # pyright: ignore[reportReturnType]  # ty: ignore[invalid-return-type]

    @_sdk_method
    async def ingest_append(
        self,
        *,
        session_id: str,
        anchor_trajectory_hash: str,
        source: str,
        trajectory: ClaudeCodeTrajectory | CodexTrajectory | CopilotTrajectory,
    ) -> IngestResponse:
        """Append a delta of transcript entries to an existing session's chain.

        The incremental counterpart to :meth:`ingest`: after a session's first
        full upload, send only the entries past the last uploaded turn
        boundary, anchored on the ``trajectory_hash`` of the last uploaded
        message. The server continues the stored chain, so rows are identical
        to a full re-upload while only the new entries travel.

        Args:
            session_id: The Xylon session UUID from the first full upload's
                response.
            anchor_trajectory_hash: The last uploaded message's trajectory
                hash; the delta is appended after it.
            source: Identifier for the data source, as in :meth:`ingest`.
            trajectory: The delta entries in Claude Code or Codex JSONL form,
                or a GitHub Copilot CLI conversation's events (led by the log's
                ``session.start``). Aperture logs have no append form.

        Raises:
            WatcherAPIError: with status 404 when the server predates the
                append route or the session is unknown, and 409 when the
                anchor cannot be appended to. Both mean: fall back to one
                full :meth:`ingest` of the whole transcript, then resume.
        """
        body = IngestAppendRequest.from_dict(
            {
                "source": source,
                "trajectory": trajectory.to_dict(),
            }
        )
        return await _ingest_append_api.asyncio_detailed(  # pyright: ignore[reportReturnType]  # ty: ignore[invalid-return-type]
            session_id=UUID(session_id),
            trajectory_hash=anchor_trajectory_hash,
            client=self._generated_client,
            body=body,
        )

    @_sdk_method
    async def upload_tool_call_decisions_batch(
        self,
        *,
        session_id: str,
        decisions: list[dict[str, Any]],
    ) -> ToolCallDecisionBatchResponse:
        """Persist tool-call decisions after transcript ingest.

        The caller should first call ``ingest`` for the same session so the server
        has canonical message rows. Each decision identifies a tool call by its
        ``tool_use_id``; the API resolves that ID before storing the decision
        and linking any pre-existing tool-call grade rows.
        """
        body = ToolCallDecisionBatchRequest.from_dict({"session_id": session_id, "decisions": decisions})
        return await _tool_call_decisions_api.asyncio_detailed(  # pyright: ignore[reportReturnType]  # ty: ignore[invalid-return-type]
            client=self._generated_client,
            body=body,
        )

    # ---- Grade ----

    @_sdk_method
    async def grade(
        self,
        *,
        session_id: str | None = None,
        trajectory_ids: list[str] | None = None,
        messages: Sequence[Sequence[ChatMessage | dict[str, Any]]] | None = None,
        grader_ids: list[str],
        tool_call_run_kind: str | None = None,
        tool_use_id: str | None = None,
    ) -> GradeResponse:
        """Grade trajectories with the named graders.

        Supports two mutually exclusive modes:

        - **DB-backed**: Provide ``session_id`` and ``trajectory_ids`` to grade
          trajectories already stored in the database.
        - **Ephemeral**: Provide ``messages`` to grade ad-hoc message lists
          directly without DB storage. Each inner list is one trajectory.

        Args:
            session_id: ID of the session containing the trajectories (DB-backed
                mode), or the session the graded call belongs to (ephemeral
                mode with ``tool_call_run_kind``).
            trajectory_ids: IDs of trajectories to grade (DB-backed mode).
            messages: List of trajectories as chat message lists (ephemeral mode).
                Each message can be a ChatMessage or a pre-serialized dict.
            grader_ids: Grader IDs to run. Required — the server has no
                default grader, and rejects a request without it (422).
            tool_call_run_kind: Optional Watcher live audit run kind. When set
                for ephemeral grading, the server persists an orphan tool-call grade
                row and returns its ID on the grade result.
            tool_use_id: The local transcript tool-use ID of the gated call
                being graded. Persisted (with ``session_id``) on the grade row
                so the later decision upload can link it even if this response
                is lost. Only valid with ``tool_call_run_kind``.

        Returns:
            GradeResponse containing grade results for each trajectory/grader pair.

        Raises:
            ValueError: If both DB-backed (trajectory_ids/session_id) and ephemeral
                (messages) modes are specified, or if neither mode is specified.
        """
        has_db = trajectory_ids is not None
        has_ephemeral = messages is not None
        # session_id rides along with ephemeral grading only to identify the
        # graded call; without a run kind it still signals DB-mode confusion.
        has_db_params = trajectory_ids is not None or (session_id is not None and tool_call_run_kind is None)
        if has_db_params and has_ephemeral:
            raise ValueError("Cannot specify both 'trajectory_ids'/'session_id' and 'messages'")
        if not has_db and not has_ephemeral:
            raise ValueError("Must specify either 'trajectory_ids' or 'messages'")
        if has_db and not session_id:
            raise ValueError("'session_id' is required when using 'trajectory_ids'")
        if has_db and tool_call_run_kind is not None:
            raise ValueError("'tool_call_run_kind' is only valid when using ephemeral 'messages'")
        if tool_use_id is not None and tool_call_run_kind is None:
            raise ValueError("'tool_use_id' is only valid with 'tool_call_run_kind'")

        if messages is not None:
            # Ephemeral mode: build the body dict manually to support pre-serialized dicts,
            # then parse into a GradeRequest for the generated function.
            body_dict: dict[str, object] = {
                "messages": [
                    [msg if isinstance(msg, dict) else msg.to_dict() for msg in trajectory] for trajectory in messages
                ],
                "grader_ids": grader_ids,
            }
            if tool_call_run_kind is not None:
                body_dict["tool_call_run_kind"] = tool_call_run_kind
            if session_id is not None:
                body_dict["session_id"] = session_id
            if tool_use_id is not None:
                body_dict["tool_use_id"] = tool_use_id
            body = GradeRequest.from_dict(body_dict)
        else:
            body = GradeRequest(
                session_id=session_id,
                trajectory_ids=trajectory_ids,
                grader_ids=grader_ids,
            )

        return await _grade_api.asyncio_detailed(client=self._generated_client, body=body)  # pyright: ignore[reportReturnType]  # ty: ignore[invalid-return-type]

    # ---- Monitors ----

    @_sdk_method
    async def list_monitors(self) -> MonitorsResponse:
        """List the server-managed monitors, with their client-facing facts.

        Each monitor carries its context policy (what of the transcript to
        assemble) and token budget (sizing facts for truncation) — never the
        monitor's prompt or model. Also the monitoring capability probe: a
        server without managed monitors raises ``WatcherNotFoundError``,
        telling the caller to grade by grader UUID instead.
        """
        return await _list_monitors_api.asyncio_detailed(client=self._generated_client)  # pyright: ignore[reportReturnType]  # ty: ignore[invalid-return-type]

    @_sdk_method
    async def grade_by_role(
        self,
        role: str,
        *,
        session_id: str | None = None,
        trajectory_ids: list[str] | None = None,
        messages: Sequence[Sequence[ChatMessage | dict[str, Any]]] | None = None,
        input: Mapping[str, Any] | None = None,  # noqa: A002 - mirrors the API field name
        tool_use_id: str | None = None,
    ) -> GradeResponse:
        """Grade with the monitor serving a role — no grader ID, model, or prompt client-side.

        Three mutually exclusive payload modes: structured ``input`` (the
        transcript and gated tool call as data, formatted into the monitor
        prompt server-side — the mode clients are expected to use), ephemeral
        ``messages`` graded as sent, or DB-backed ``session_id`` +
        ``trajectory_ids``. The server resolves the role's grader, prompt
        (with the org's custom instructions injected), model, and reasoning;
        non-DB grades persist as tool-call audit rows under the role's run
        kind and return a ``tool_call_grade_id`` per result. ``model`` is null
        on results. ``cost_usd`` estimates this request's cost across all
        trajectories and reported retry usage, at prices set on the server.
        It is null when usage or prices are missing, or the caller cannot read
        the stored session's findings or content, and absent on older servers.

        Args:
            role: A client-invocable monitor role (``"triage"`` or ``"gateway"``).
            session_id: ID of the session containing the trajectories (DB-backed
                mode), or the session the graded call belongs to, persisted on
                the tool-call grade row (``input``/``messages`` modes).
            trajectory_ids: IDs of trajectories to grade (DB-backed mode).
            messages: List of trajectories as chat message lists (ephemeral mode).
            input: Structured monitoring input as a dict matching the API's
                ``MonitoringInput`` shape (``messages``, ``tool_name``,
                ``tool_input``, ``cwd``, ``triage_assessment``,
                ``prior_decisions``, ``grading_guidelines``). Send the
                transcript as structured ``messages`` (chat-message dicts the
                server renders under the monitor's context policy); the
                pre-rendered ``transcript`` parts form is deprecated and kept
                only for the client-compatibility window.
            tool_use_id: The local transcript tool-use ID of the gated call
                being graded, persisted (with ``session_id``) on the grade row
                so the later decision upload can link it even if this response
                is lost. Ephemeral modes only.

        Raises:
            ValueError: Unless exactly one payload mode is specified.
        """
        has_db = trajectory_ids is not None
        modes = sum([has_db, messages is not None, input is not None])
        if modes != 1:
            raise ValueError("Specify exactly one of 'input', 'messages', or 'trajectory_ids' (+ session_id)")
        if has_db and not session_id:
            raise ValueError("'session_id' is required when using 'trajectory_ids'")
        if has_db and tool_use_id is not None:
            raise ValueError("'tool_use_id' is only valid with ephemeral 'input' or 'messages' grading")

        if input is not None or messages is not None:
            body_dict: dict[str, object] = {}
            if input is not None:
                body_dict["input"] = dict(input)
            else:
                assert messages is not None
                body_dict["messages"] = [
                    [msg if isinstance(msg, dict) else msg.to_dict() for msg in trajectory] for trajectory in messages
                ]
            if session_id is not None:
                body_dict["session_id"] = session_id
            if tool_use_id is not None:
                body_dict["tool_use_id"] = tool_use_id
            body = MonitoringRequest.from_dict(body_dict)
        else:
            body = MonitoringRequest(session_id=session_id, trajectory_ids=trajectory_ids)

        return await _grade_by_monitor_api.asyncio_detailed(  # pyright: ignore[reportReturnType]  # ty: ignore[invalid-return-type]
            GradeByMonitorV1MonitorsRoleGradePostRole(role),
            client=self._generated_client,
            body=body,
        )

    @overload
    async def pre_tool_use_hook(
        self,
        input: Mapping[str, Any] | list[_HookInputMapping] | None = None,
        *,
        messages: Sequence[Mapping[str, Any]] | Mapping[str, Any] | None = None,
        append_after: Mapping[str, str],
        external_ids: Mapping[str, str | None] | None = None,
        tool_use_id: str | None = None,
        user: str | None = None,
        ephemeral: bool | None = None,
        mode: str | None = None,
        force_regrade: bool = False,
        timeout: float | None = None,
        skip_rules: bool | None = None,
        policy_version: str | None = None,
        settings_overrides: str | dict[str, Any] | None = None,
    ) -> HookAppendResponse: ...

    @overload
    async def pre_tool_use_hook(
        self,
        input: Mapping[str, Any],
        *,
        messages: Sequence[Mapping[str, Any]] | Mapping[str, Any] | None = None,
        append_after: None = None,
        external_ids: Mapping[str, str | None] | None = None,
        tool_use_id: str | None = None,
        user: str | None = None,
        ephemeral: bool | None = None,
        mode: str | None = None,
        force_regrade: bool = False,
        timeout: float | None = None,
        skip_rules: bool | None = None,
        policy_version: str | None = None,
        settings_overrides: str | dict[str, Any] | None = None,
    ) -> PreToolUseHookResponse: ...

    @overload
    async def pre_tool_use_hook(
        self,
        input: list[_HookInputMapping] | None = None,
        *,
        messages: Sequence[Mapping[str, Any]] | Mapping[str, Any] | None = None,
        append_after: None = None,
        external_ids: Mapping[str, str | None] | None = None,
        tool_use_id: None = None,
        user: str | None = None,
        ephemeral: bool | None = None,
        mode: str | None = None,
        force_regrade: bool = False,
        timeout: float | None = None,
        skip_rules: bool | None = None,
        policy_version: str | None = None,
        settings_overrides: str | dict[str, Any] | None = None,
    ) -> list[PreToolUseHookResponse | HookCallError]: ...

    @overload
    async def pre_tool_use_hook(
        self,
        input: None = None,
        *,
        request_body: Mapping[str, Any],
        response_body: Mapping[str, Any],
        url: str = "",
        provider: str | None = None,
        user_agent: str | None = None,
        response_index: int | None = None,
        external_ids: Mapping[str, str | None] | None = None,
        user: str | None = None,
        ephemeral: bool | None = None,
        mode: str | None = None,
        force_regrade: bool = False,
        timeout: float | None = None,
        skip_rules: bool | None = None,
        policy_version: str | None = None,
        settings_overrides: str | dict[str, Any] | None = None,
    ) -> list[PreToolUseHookResponse | HookCallError]: ...

    async def pre_tool_use_hook(
        self,
        input: Mapping[str, Any] | list[_HookInputMapping] | None = None,
        *,
        messages: Sequence[Mapping[str, Any]] | Mapping[str, Any] | None = None,
        append_after: Mapping[str, str] | None = None,
        external_ids: Mapping[str, str | None] | None = None,
        tool_use_id: str | None = None,
        user: str | None = None,
        ephemeral: bool | None = None,
        mode: str | None = None,
        force_regrade: bool = False,
        timeout: float | None = None,
        skip_rules: bool | None = None,
        policy_version: str | None = None,
        settings_overrides: str | dict[str, Any] | None = None,
        request_body: Mapping[str, Any] | None = None,
        response_body: Mapping[str, Any] | None = None,
        url: str = "",
        provider: str | None = None,
        user_agent: str | None = None,
        response_index: int | None = None,
    ) -> HookAppendResponse | PreToolUseHookResponse | list[PreToolUseHookResponse | HookCallError]:
        """Evaluate tool calls or ingest a transcript through Watcher's server pipeline.

        Enforce runs the hierarchical funnel (per-tool thresholds, command rules,
        triage monitor, gateway monitor) against the org's managed settings
        and returns a decision with full provenance. Graded calls can take
        tens of seconds; deterministic decisions return in milliseconds.
        Observe runs the same pipeline and returns its completed judgment and
        stage results, with `decision="deferred"` so the caller does not enforce
        that judgment. Both modes support ephemeral evaluation and evaluation
        without session-write permission for full requests; append requests
        require authority to write the named session and cannot be ephemeral.

        A list accepts at most 32 inputs, evaluates its calls concurrently against
        one shared conversation, and returns completed responses in input order.
        Larger lists are rejected with HTTP 422.
        Without `append_after`, null, omitted, or empty input ingests `messages`
        and returns an empty list. Successful appends return `HookAppendResponse`:
        `results` contains the scalar judgment, the batch's ordered results,
        or an empty list for ingestion only. Its `append_after` names the
        committed last message and is ready for the next append.
        A failed batch item returns `HookCallError` in that position and
        subsequent calls still run. Every batch outcome echoes its input's
        `tool_use_id`, or null when omitted. Scalar monitor refusals remain HTTP
        errors and occur before an append's delta is stored.
        A scalar input with an explicitly blank `tool_name` only ingests its transcript under any
        enforcement setting. Paused settings also skip evaluation. Both bypass
        grading admission and return deferred without a judgment or decision
        record; authorized transcript ingestion still uses database resources. Evaluated decisions
        are recorded against each input's `tool_use_id`, with the conversation
        mirrored as a session, when the key permits session ingestion and
        `ephemeral` is false.

        Unlike other SDK methods, this one performs no automatic transport
        retries: the server deliberately lets a disconnected request's grading
        run to completion (its usage still counts against the org's monthly
        allowance), so a blind timeout/5xx retry can multiply billed grading
        pipelines for one tool decision. A timeout or transient failure
        surfaces immediately, and a caller that retries owns that choice and
        its cost. Unlike other methods this one also does not use the client's
        default timeout: a full-mode grade legitimately takes tens of seconds
        to minutes, so the request runs under its own `timeout` (default
        420 seconds per input, sized past the server's full grading ceiling).
        Batch defaults conservatively scale with input count because concurrency
        is shared with other requests; an explicit
        `timeout` remains the budget for the whole request. Pass a smaller
        `timeout` — or send
        `mode="triage_only"` — when the budget is tight.

        Pass `request_body` and `response_body` instead of `input` and
        `messages` to send a raw provider pair (the server's `format="raw"`):
        a gateway's provider request and its complete, non-streaming response
        in OpenAI Chat Completions or Responses, Anthropic Messages, Gemini
        generateContent or Bedrock Converse format, plus the client-facing
        endpoint path in `url`. The server converts the pair, recognizes known
        coding harnesses from the bodies and `user_agent`, and evaluates the
        selected new client calls. The result is a list with one output per
        selected call in response order. Each output's `tool_use_id` is the
        provider's call ID in `response_body`; Gemini calls get generated IDs
        and are matched by order within the selected candidate. `response_index`
        selects a Chat choice or Gemini candidate by zero-based array position.
        It is required when there are several; deliver only that alternative.

        Match every executable client call you will deliver to exactly one
        output before applying its decision. Withhold the response if a call
        has no output, IDs are duplicated, or an output cannot be matched to
        a call. For Gemini, require equal call and output counts. Anthropic
        calls before the final `fallback` block have no output. An empty list
        means no client calls were selected, not that the original response
        contains none. An error output is not permission to execute a call.

        There is no limit on the number of tool calls in one response.
        `tool_use_id` does not apply as an argument. The default timeout is
        420 seconds for the whole request.

        Args:
            input: One call, a list sharing the same messages, or None for ingestion only,
                each matching the API's `MonitoringInput` shape —
                `{"tool_name": ..., "tool_input": ..., "tool_use_id": ...,
                "cwd": ..., "messages": [...], "prior_decisions": [...],
                "grading_guidelines": ...}`. For multiple inputs, supply one
                top-level `messages` transcript and omit each input's messages
                (null or empty nested lists are also accepted). A scalar or
                one-item list may instead carry its transcript in the input.
                An empty transcript is accepted: the conversation as structured
                chat-message dicts (`{"role": ..., "content": ...}`), which
                the server renders under each monitor's served context policy —
                decisions improve with it since the monitors score
                intent-in-context. The pre-rendered `transcript` form is
                rejected on this surface, and `triage_assessment` is
                server-populated and rejected if supplied. Structured inputs
                use `format="watcher"`; raw provider pairs use the separate
                `request_body` and `response_body` arguments.
            messages: The conversation the calls are judged in, in one of two forms.

                - Structured chat-message mappings (``format="watcher"``).
                  Required for multiple inputs, None, or an empty list. A
                  multi-input batch rejects any nonempty nested `messages`.
                  With one input, top-level and nested transcripts must match
                  if both are non-null.
                - The coding agent's own transcript file, the shape `ingest`
                  accepts: ``{"format": "claude-code-jsonl" | "codex-jsonl" |
                  "copilot-events-jsonl", "timestamp": ..., "entries": [...]}``
                  (a Copilot conversation also names its ``agent_id``, null for
                  the parent). The request takes that format. The calls are
                  judged with the file's live branch as context; the file is
                  stored up to its last complete tool cycle, as a direct upload
                  would store it. Inputs never carry their own `messages` then.
                  Each call should name its `tool_use_id`: Claude Code's hooks
                  report it; for Codex read it from the rollout
                  (`watcher_transcript_transport.codex.pending_call_id`). A
                  Codex call without one, or one the rollout does not hold, is
                  never allowed by a command rule; the monitors decide. A
                  Copilot call names the ID its log's hook record gives it, under
                  Copilot's native tool name and arguments, and must match the
                  log's record of that ID exactly.

                With `append_after`, send only what follows the anchor (chat
                messages or file entries); an empty delta can evaluate a call
                already stored.
            append_after: A mapping containing the
                stored `session_id` UUID string and `trajectory_id` of the last
                message already sent. The server restores that exact prefix
                before validation and evaluation, so selected calls may appear
                in earlier uploads. The anchor must still be continuable; the
                server never chooses a branch implicitly. Bootstrap the initial
                anchor through ingestion or a verified `search_sessions` result.
                A successful append waits for transcript and available decision
                recording, then returns `HookAppendResponse`. Pass
                `response.append_after.to_dict()` on the next append without
                searching again. Never advance the cursor after a failure:
                recording can return HTTP 503 with `code="append_recording_failed"`
                after the delta commits. For that code, `WatcherAPIError.body`
                retains the ordered `results` list without a new cursor. Apply
                those decisions, including denies, before using a generic 5xx
                failure policy. Older servers may omit `results`; handle that
                absence with your normal failure policy. The caller may retry
                the same append to finish recording; retries
                are not automatic and may repeat grading. Append cannot be
                combined with `ephemeral=True`. On HTTP 404, 409, or 422,
                retry once with the full conversation and omit `append_after`.
                HTTP 422 also covers older servers rejecting the new field.
                The SDK does not perform this fallback: it has no stored copy
                of the prefix. A full fallback still has the normal body-size
                limit; surface its failure instead of repeatedly retrying.
                Full hook responses do not return an anchor, so obtain and
                verify another stored anchor before resuming deltas after fallback.
            external_ids: Distinct conversation IDs from the harness and gateway,
                keyed by source (`"claude_code"`, `"codex"`, `"aperture"`,
                `"other"` for the gateway's own id); a recorded session
                converges with the one Watcher Live or the Aperture log ingest
                created for the same conversation. Required unless
                `ephemeral`; send every id you have. A caller with none
                records id-less with an explicit `None` value
                (`{"other": None}`), and the server then finds the session by
                transcript prefix. The harness is read off the keys. For
                append requests, keep the harness and non-null IDs consistent
                with the stored session; the anchor selects the session.
                Append needs the matching harness key: send
                `{"claude_code": None}` or `{"codex": None}` when its ID is
                unknown. Omitting that key for those sessions returns HTTP 409.
            tool_use_id: Scalar-input convenience for `input.tool_use_id`.
                Rejected with list or None input; supply each item's own ID instead.
                Evaluated, recorded inputs need an ID matching a tool call in
                their messages; repeating that ID converges onto one record.
            user: Email of the watched developer to attribute the mirrored
                session to — honored only for callers allowed to impersonate.
            ephemeral: Set True to skip tool-call grade rows, transcripts, and
                decision records (server default False). Usage accounting and
                configured admin-access auditing still apply. Enforce and observe
                return the completed judgment; observe applies a deferred decision.
                Cannot be combined with `append_after`; the SDK raises `ValueError`
                before sending a request, and the server rejects it with HTTP 422.
            mode: `"full"` (the server default) or `"triage_only"` to skip
                the slow gateway grade — triage can clear a call but never
                deny, so an uncleared call is judged `escalate`. Both modes
                return that judgment; observe applies a deferred decision.
            force_regrade: Set True to bypass reuse of a completed evaluation
                and evaluate again. Rules still run unless `skip_rules` is set.
            skip_rules: Set True when the caller already ran the deterministic
                stages in-process (see `pre_tool_use`) — the server goes
                straight to grading, and the caller owns the rules outcome.
                Honored as-is; pass `policy_version` too for a snapshot check.
            policy_version: Optional. The policy snapshot the caller evaluated
                against, as `<version>@<builtin digest>`: the resolved
                managed-settings document's `version` plus
                `builtin_settings_digest()` of this package's builtins
                (`pre_tool_use` derives it). When given, the server compares
                it with its own effective policy's token and runs the
                deterministic stages itself on a mismatch, so both halves of
                the decision share one policy snapshot.
            settings_overrides: YAML text or a JSON mapping the server will merge onto the
                org baseline like a machine's `settings.local.yaml`.
                `enforcement.mode` selects `enforce`, `observe` (evaluate with
                a deferred applied decision), or `paused` (ingest only). Changing an admin-locked value
                is rejected with HTTP 422; repeating the locked value is accepted.

        """
        if append_after is not None and ephemeral is True:
            raise ValueError("append_after cannot be combined with ephemeral=True")
        if request_body is not None or response_body is not None:
            if request_body is None or response_body is None:
                raise ValueError("A raw pair needs both request_body and response_body")
            if append_after is not None:
                raise ValueError("append_after is only supported with watcher-format messages")
            if input is not None or messages is not None or tool_use_id is not None:
                raise ValueError("A raw pair replaces input, messages and tool_use_id; do not combine them")
            raw: dict[str, object] = {
                "format": "raw",
                "request_body": dict(request_body),
                "response_body": dict(response_body),
                "url": url,
            }
            optional: dict[str, object | None] = {
                "provider": provider,
                "user_agent": user_agent,
                "response_index": response_index,
                "external_ids": dict(external_ids) if external_ids is not None else None,
                "user": user,
                "mode": mode,
                "ephemeral": ephemeral,
                "skip_rules": skip_rules,
                "policy_version": policy_version,
                "settings_overrides": settings_overrides,
            }
            raw.update({key: value for key, value in optional.items() if value is not None})
            if force_regrade:
                raw["force_regrade"] = True
            return await self._send_pre_tool_use_hook(
                RawPreToolUseHookRequest.from_dict(raw),
                timeout if timeout is not None else _HOOK_REQUEST_TIMEOUT_SECONDS,
            )
        if isinstance(messages, Mapping) and messages.get("format") not in _TRANSCRIPT_FILE_FORMATS:
            raise ValueError(
                "A transcript file in messages must be claude-code-jsonl, codex-jsonl or copilot-events-jsonl"
            )
        if input is None or isinstance(input, list):
            if tool_use_id is not None:
                raise ValueError("tool_use_id is only supported for scalar input; set each input.tool_use_id instead")
            hook_input: dict[str, Any] | list[dict[str, Any]] | None = (
                None if input is None else [dict(item) for item in input]
            )
        else:
            hook_input = dict(input)
            if tool_use_id is not None:
                hook_input["tool_use_id"] = tool_use_id
        body_dict: dict[str, object] = {"format": "watcher", "input": hook_input}
        if isinstance(messages, Mapping):
            body_dict["format"] = messages["format"]
            body_dict["messages"] = dict(messages)
        elif messages is not None:
            body_dict["messages"] = [dict(message) for message in messages]
        if append_after is not None:
            body_dict["append_after"] = dict(append_after)
        if external_ids is not None:
            body_dict["external_ids"] = dict(external_ids)
        if user is not None:
            body_dict["user"] = user
        if ephemeral is not None:
            body_dict["ephemeral"] = ephemeral
        if mode is not None:
            body_dict["mode"] = mode
        if force_regrade:
            body_dict["force_regrade"] = True
        if skip_rules is not None:
            body_dict["skip_rules"] = skip_rules
        if policy_version is not None:
            body_dict["policy_version"] = policy_version
        if settings_overrides is not None:
            body_dict["settings_overrides"] = settings_overrides
        input_count = max(1, len(input)) if isinstance(input, list) else 1
        body = (
            ClaudeCodeHookRequest.from_dict(body_dict)
            if body_dict["format"] == "claude-code-jsonl"
            else CodexHookRequest.from_dict(body_dict)
            if body_dict["format"] == "codex-jsonl"
            else CopilotHookRequest.from_dict(body_dict)
            if body_dict["format"] == "copilot-events-jsonl"
            else PreToolUseHookRequest.from_dict(body_dict)
        )
        return await self._send_pre_tool_use_hook(
            body,
            timeout if timeout is not None else _HOOK_REQUEST_TIMEOUT_SECONDS * input_count,
        )

    async def _send_pre_tool_use_hook(
        self,
        body: PreToolUseHookRequest
        | ClaudeCodeHookRequest
        | CodexHookRequest
        | CopilotHookRequest
        | RawPreToolUseHookRequest,
        timeout: float,
    ) -> HookAppendResponse | PreToolUseHookResponse | list[PreToolUseHookResponse | HookCallError]:
        """POST one hook request under its own timeout, without the client's automatic retries."""
        request_kwargs = _pre_tool_use_hook_api._get_kwargs(body=body)
        request_kwargs["timeout"] = timeout
        try:
            raw = await self._generated_client.get_async_httpx_client().request(**request_kwargs)
        except httpx.ConnectError as e:
            raise WatcherConnectionError(str(e)) from e
        except httpx.TimeoutException as e:
            raise WatcherTimeoutError(str(e)) from e
        # Check the status before the generated parser reads the body: it
        # expects the documented error shape and would otherwise raise on any
        # other 422 body, losing the status.
        _raise_for_http_error(raw.status_code, raw.content, raw.headers)
        response = _pre_tool_use_hook_api._build_response(client=self._generated_client, response=raw)
        return response.parsed  # pyright: ignore[reportReturnType]  # ty: ignore[invalid-return-type]

    async def aperture_entire_request_hook(self, payload: Mapping[str, Any]) -> ApertureHookAccepted:
        """Submit an Aperture entire-request delivery for asynchronous processing.

        Pass the webhook envelope with `metadata`, `request_body`, and
        `response_body`; metadata must contain `login_name`, `request_id`,
        `provider`, and `url`. Requires an API key with `sessions:write:any`.
        Only Claude Code conversations in Anthropic Messages format are
        supported. The administrator's enforcement setting selects observation
        or ingestion only; this asynchronous hook cannot enforce guardrails.

        The acknowledgement confirms admission to a bounded in-memory worker,
        not completed grading or durable storage. This method never retries
        automatically: a timeout may follow acceptance, and repeating delivery
        can duplicate billed grading. Transport and API failures surface as
        the SDK's typed exceptions.
        """
        body = ApertureHookRequest.from_dict(payload)
        try:
            response = await _aperture_entire_request_hook_api.asyncio_detailed(
                client=self._generated_client, body=body
            )
        except httpx.ConnectError as e:
            raise WatcherConnectionError(str(e)) from e
        except httpx.TimeoutException as e:
            raise WatcherTimeoutError(str(e)) from e
        _raise_for_response(response)
        return response.parsed  # pyright: ignore[reportReturnType]  # ty: ignore[invalid-return-type]

    async def _org_hook_baseline(self) -> _HookBaseline | None:
        """The org baseline for local deterministic evaluation, cached.

        The same resolution the hook endpoint performs server-side: the org's
        resolved managed-settings document merged onto the packaged builtins,
        together with that document's version token so the server can verify
        the local stage ran against the same policy it grades under.
        Returns `None` — decline local evaluation, defer to the server —
        whenever the fetched baseline cannot be confirmed to be the policy the
        hook endpoint would enforce: the resolve route answers its expected 404
        for both "nothing saved" and "the org distributes via MDM", and in the
        MDM case the endpoint may still read a retained document this client
        cannot see, so treating 404 as "builtins" could enforce the wrong rules
        locally. A 403 (an API key without `org:settings:read` — the hook
        endpoint itself needs no such permission) declines the same way rather
        than failing the caller's hook. An unparseable document retains builtin
        restrictions but disables command-rule approvals, matching the server.

        A result — tree or decline — serves for `_HOOK_BASELINE_TTL_SECONDS`;
        past the TTL a failed re-fetch falls back to the last-known-good result
        rather than failing the caller's hook, matching watcher-live's handling
        of its settings layer. Only the first-ever fetch propagates transport
        errors, since there is nothing safe to serve yet.
        """
        now = time.monotonic()
        cached = self._hook_baseline_cache
        if cached is not None and (now - cached[1]) < _HOOK_BASELINE_TTL_SECONDS:
            return cached[0]
        overlay: dict[str, Any] | None = None
        version_token: str | None = None
        declined = False
        try:
            resolved = await self.resolve_org_managed_settings()
            # The same token the server builds for its own policy: document
            # version plus the packaged builtins' fingerprint, so a client
            # whose builtins lag the server's is caught as a mismatch.
            version_token = f"{resolved.version}@{builtin_settings_digest()}"
            parsed = load_settings_yaml(resolved.yaml)
            if isinstance(parsed, dict):
                overlay = parsed
            elif parsed is None:
                overlay = {}
        except WatcherNotFoundError:
            declined = True  # unmanaged or MDM: only the server can tell which
        except (YAMLError, ValueError):
            pass  # unreadable policy keeps known restrictions but cannot approve by rule
        except WatcherAPIError as e:
            if e.status_code == 403:
                declined = True  # this key cannot read settings; the endpoint can
            elif cached is not None:
                return cached[0]
            else:
                raise
        except (WatcherConnectionError, WatcherTimeoutError):
            # A network blip or a slow answer past the TTL: serve the
            # last-known-good baseline rather than fail the caller's hook.
            if cached is not None:
                return cached[0]
            raise
        baseline = (
            None
            if declined or version_token is None
            else _HookBaseline(
                settings=merge_policy_settings(load_builtin_settings("settings.yaml"), overlay),
                version_token=version_token,
            )
        )
        self._hook_baseline_cache = (baseline, now)
        return baseline

    @overload
    async def pre_tool_use(
        self,
        input: Mapping[str, Any],
        *,
        messages: Sequence[Mapping[str, Any]] | None = None,
        external_ids: Mapping[str, str | None] | None = None,
        tool_use_id: str | None = None,
        user: str | None = None,
        ephemeral: bool | None = None,
        mode: str | None = None,
        force_regrade: bool = False,
        settings_overrides: str | dict[str, Any] | None = None,
    ) -> PreToolUseHookResponse | LocalPreToolUseDecision: ...

    @overload
    async def pre_tool_use(
        self,
        input: list[_HookInputMapping] | None = None,
        *,
        messages: Sequence[Mapping[str, Any]] | None = None,
        external_ids: Mapping[str, str | None] | None = None,
        tool_use_id: None = None,
        user: str | None = None,
        ephemeral: bool | None = None,
        mode: str | None = None,
        force_regrade: bool = False,
        settings_overrides: str | dict[str, Any] | None = None,
    ) -> list[PreToolUseHookResponse | HookCallError]: ...

    async def pre_tool_use(
        self,
        input: Mapping[str, Any] | list[_HookInputMapping] | None = None,
        *,
        messages: Sequence[Mapping[str, Any]] | None = None,
        external_ids: Mapping[str, str | None] | None = None,
        tool_use_id: str | None = None,
        user: str | None = None,
        ephemeral: bool | None = None,
        mode: str | None = None,
        force_regrade: bool = False,
        settings_overrides: str | dict[str, Any] | None = None,
    ) -> PreToolUseHookResponse | LocalPreToolUseDecision | list[PreToolUseHookResponse | HookCallError]:
        """Evaluate scalar calls locally when possible; send batches to the server.

        The watcher-live split for integrators, in one call. The org baseline
        (resolved managed settings merged onto the packaged builtins, cached —
        see `_org_hook_baseline`) is evaluated locally through the same
        shared implementation the hook endpoint runs. A call the terminal
        thresholds or command rules decide returns a `LocalPreToolUseDecision`
        at zero latency, posture-applied against that cached baseline; everything
        else goes to `pre_tool_use_hook` with `skip_rules` set. The server
        reruns deterministic stages if its policy snapshot differs, and otherwise
        runs only the graded stages. A rule-engine failure (a pathological
        pattern hitting the match timeout included) degrades to grading rather
        than deciding — the same containment the endpoint applies.

        The local stage runs only with a readable administrator baseline;
        locally returned decisions use that cached policy. It also steps aside
        for a request whose `external_ids` name Claude Code or Codex when the
        tool name is not one the packaged settings configure: the endpoint
        evaluates such calls under a translated Claude Code tool name (Codex's
        `exec_command` as `Bash`), which this client cannot reproduce. When it cannot be read — the
        org has no readable settings document (which also covers MDM-distributed
        settings the endpoint may still resolve differently), or the caller's
        key cannot read settings — every call goes to the server, which owns
        policy resolution (see `_org_hook_baseline`).

        `settings_overrides` applies to both halves through the same
        shared merge the server runs: the local stage evaluates the overlaid
        tree, and graded calls carry the same overlay for the server to apply
        to its baseline. An override changing an admin-locked value raises
        `ValueError` locally, before any evaluation (the server would answer
        422 for the same document).

        Set `enforcement.mode` in `settings_overrides` to change the mode.
        Repeating a locked value is accepted. Observe returns deferred local judgments;
        paused sends the transcript to the server for ingestion. Scalars with an
        explicitly blank `tool_name`, omitted or None input, and all batches go
        directly to the server without fetching settings. Server-delegated
        observe calls return completed judgments with a deferred applied decision.
        Ephemeral calls and calls without session-write permission still return
        judgments, without recording a transcript or decision.
        Batches preserve input order with `HookCallError` entries for
        failed items; successful items are retained and later items still run.
        Multi-input batches require one top-level `messages` transcript and reject
        nonempty nested transcripts.
        None or an empty list ingests `messages` and returns an empty list.
        Delegated calls use `pre_tool_use_hook`'s default timeout
        of 420 seconds per input, conservatively including every batch item.

        Before local evaluation, a selected `tool_use_id` must occur in a supplied
        transcript unless `ephemeral=True`. Every occurrence must match `tool_name`
        and `tool_input`, or `ValueError` is raised. The convenience ID overrides
        the nested ID. Argument comparison
        ignores object key order but preserves JSON types; omitted `tool_input`
        means `{}`, while explicit null does not. Top-level and nested transcripts
        that differ apart from message IDs go to the server for normalization and
        validation before any evaluation.

        `force_regrade=True` requests a fresh server evaluation, bypassing the
        local fast path and the server's completed-result reuse.

        Locally decided calls make no hook request, so they do not enter the
        session record; `external_ids`/`tool_use_id` and the other
        recording parameters apply to calls sent to the server (see `pre_tool_use_hook`
        for all parameter semantics). Callers that need every decision
        recorded call the endpoint directly instead.
        """
        if input is None or isinstance(input, list):
            if tool_use_id is not None:
                raise ValueError("tool_use_id is only supported for scalar input; set each input.tool_use_id instead")
            return await self.pre_tool_use_hook(
                input,
                messages=messages,
                external_ids=external_ids,
                user=user,
                ephemeral=ephemeral,
                mode=mode,
                force_regrade=force_regrade,
                settings_overrides=settings_overrides,
            )
        if force_regrade:
            return await self.pre_tool_use_hook(
                input,
                messages=messages,
                external_ids=external_ids,
                tool_use_id=tool_use_id,
                user=user,
                ephemeral=ephemeral,
                mode=mode,
                force_regrade=True,
                settings_overrides=settings_overrides,
            )
        normalized_input = _validate_local_hook_identity(input, messages, tool_use_id, is_ephemeral=ephemeral is True)
        pending_tool_name = input.get("tool_name")
        baseline = (
            await self._org_hook_baseline()
            if normalized_input is not None and isinstance(pending_tool_name, str) and pending_tool_name.strip()
            else None
        )
        if baseline is None:
            # The server owns transcript normalization, policy resolution without
            # a confirmed baseline, and ingestion-only requests.
            return await self.pre_tool_use_hook(
                input,
                messages=messages,
                external_ids=external_ids,
                tool_use_id=tool_use_id,
                user=user,
                ephemeral=ephemeral,
                mode=mode,
                settings_overrides=settings_overrides,
            )
        assert normalized_input is not None
        input = normalized_input
        tree = baseline.settings
        if settings_overrides is not None:
            tree = merge_local_overrides(tree, settings_overrides)
        enforcement = unwrap(get_path_or_none(tree, ("enforcement", "mode")))
        if enforcement == "paused":
            return await self.pre_tool_use_hook(
                input,
                messages=messages,
                external_ids=external_ids,
                tool_use_id=tool_use_id,
                user=user,
                ephemeral=ephemeral,
                mode=mode,
                settings_overrides=settings_overrides,
            )
        tool_name = str(input["tool_name"])
        if _hook_may_translate(external_ids, tool_name):
            # The server evaluates this call under a translated name the local
            # stage cannot reproduce, so it runs every stage there. It requires
            # a transcript even for an ephemeral call, which the local stage did
            # not, so an ephemeral call sent without one carries an empty one.
            no_transcript = messages is None and input.get("messages") is None
            return await self.pre_tool_use_hook(
                input,
                messages=[] if no_transcript and ephemeral is True else messages,
                external_ids=external_ids,
                tool_use_id=tool_use_id,
                user=user,
                ephemeral=ephemeral,
                mode=mode,
                settings_overrides=settings_overrides,
            )
        tool_input = input.get("tool_input")
        thresholds = resolve_tool_thresholds_from_tree(tree, tool_name)
        terminal = terminal_rule_action(thresholds.flag_threshold, thresholds.deny_threshold)
        match: CommandRuleMatch | None = None
        source = "threshold"
        if terminal is not None:
            match = CommandRuleMatch(
                action=terminal, label=TERMINAL_THRESHOLD_LABEL, pattern=TERMINAL_THRESHOLD_PATTERN
            )
        else:
            source = "rule"
            try:
                match = evaluate_command_rules(
                    tool_name,
                    tool_input,
                    command_rules_from_tree(tree),
                    None,
                    match_timeout=_LOCAL_RULE_MATCH_TIMEOUT_SECONDS,
                )
            except Exception:
                match = None  # rule-engine failures degrade to grading, never decide
        judged = _LOCAL_JUDGMENTS.get(match.action) if match is not None else None
        if match is not None and judged is not None:
            return LocalPreToolUseDecision(
                decision=apply_org_posture(judged, enforcement),
                judged_decision=judged,
                decision_source=source,
                enforcement_mode=enforcement,
                rule_label=match.label,
                rule_pattern=match.pattern,
                rule_action=match.action,
            )
        return await self.pre_tool_use_hook(
            input,
            messages=messages,
            external_ids=external_ids,
            tool_use_id=tool_use_id,
            user=user,
            ephemeral=ephemeral,
            mode=mode,
            skip_rules=True,
            policy_version=baseline.version_token,
            settings_overrides=settings_overrides,
        )

    # ---- Graders ----

    @_sdk_method
    async def list_graders(
        self,
        limit: int = 100,
        offset: int = 0,
    ) -> GraderListResponse:
        """List all available graders with their score definitions.

        Args:
            limit: Maximum number of graders to return per page.
            offset: Number of graders to skip (for pagination).

        Returns:
            GraderListResponse containing the graders and the total count.
        """
        return await _list_graders_api.asyncio_detailed(client=self._generated_client, limit=limit, offset=offset)  # pyright: ignore[reportReturnType]  # ty: ignore[invalid-return-type]

    @_sdk_method
    async def create_grader(
        self,
        name: str,
        header: str,
        scores: Mapping[str, Mapping[str, object]],
        description: str | None = None,
        footer: str | None = None,
        default_model: str | None = None,
        include_thinking: bool = True,
        include_explanation: bool = True,
        include_summary: bool = True,
        reasoning_effort: str | None = None,
        reasoning_tokens: int | None = None,
        public: bool = False,
    ) -> GraderDetail:
        """Create a new grader (version 0).

        Args:
            name: Human-readable name for the grader.
            header: Text before the score definitions section in the grading prompt.
            scores: Score definitions mapping score name to its definition.
                Each definition should have at least 'type' and 'description' keys.
            description: Optional description of the grader.
            footer: Optional text after the score definitions section (e.g., Score Adjustments).
            default_model: Optional default model to use for grading.
            include_thinking: Whether to include thinking in grading output.
            include_explanation: Whether to include explanation in grading output.
            include_summary: Whether to include summary in grading output.
            reasoning_effort: Optional native-reasoning effort for the grading model
                (one of none/minimal/low/medium/high/xhigh/max). Mutually exclusive
                with reasoning_tokens.
            reasoning_tokens: Optional native-reasoning token budget for
                budget-controlled models (0 disables thinking). Mutually exclusive
                with reasoning_effort.
            public: If True, every member of the org can see the grader. If False
                (default), only the creator and admins can see it.

        Returns:
            GraderDetail of the newly created grader.
        """
        body = CreateGraderRequest(
            name=name,
            header=header,
            scores=CreateGraderRequestScores.from_dict(scores),
            description=description,
            footer=footer,
            default_model=default_model,
            include_thinking=include_thinking,
            include_explanation=include_explanation,
            include_summary=include_summary,
            reasoning_effort=(
                None if reasoning_effort is None else CreateGraderRequestReasoningEffortType0(reasoning_effort)
            ),
            reasoning_tokens=reasoning_tokens,
            public=public,
        )
        return await _create_grader_api.asyncio_detailed(client=self._generated_client, body=body)  # pyright: ignore[reportReturnType]  # ty: ignore[invalid-return-type]

    @_sdk_method
    async def get_grader(self, grader_id: str, version: int | None = None) -> GraderDetail:
        """Get full grader detail by ID, optionally pinned to a specific version.

        Without ``version``, returns the latest non-archived version. With
        ``version``, returns that exact version even if archived (useful for
        grade provenance lookups).

        Args:
            grader_id: UUID of the grader to retrieve.
            version: Optional version number. If omitted, returns the latest
                non-archived version.

        Returns:
            GraderDetail with full grader information including header and footer.

        Raises:
            WatcherNotFoundError: If no grader (or version) exists with the given ID.
        """
        if version is not None:
            return await _get_grader_version_api.asyncio_detailed(grader_id, version, client=self._generated_client)  # pyright: ignore[reportReturnType]  # ty: ignore[invalid-return-type]
        return await _get_grader_api.asyncio_detailed(grader_id, client=self._generated_client)  # pyright: ignore[reportReturnType]  # ty: ignore[invalid-return-type]

    @_sdk_method
    async def update_grader(
        self,
        grader_id: str,
        **updates: object,
    ) -> GraderDetail:
        """Create a new grader version with the given updates.

        Args:
            grader_id: UUID of the grader to update.
            **updates: Fields to update. Valid keys: name, description, header,
                footer, scores, default_model, include_thinking, include_explanation,
                include_summary, reasoning_effort, reasoning_tokens.

        Returns:
            GraderDetail with the new grader version.

        Raises:
            WatcherNotFoundError: If no grader exists with the given ID.
        """
        body = UpdateGraderRequest.from_dict(updates)
        return await _update_grader_api.asyncio_detailed(grader_id, client=self._generated_client, body=body)  # pyright: ignore[reportReturnType]  # ty: ignore[invalid-return-type]

    @_sdk_method
    async def delete_grader(self, grader_id: str) -> None:
        """Archive all versions of a grader (soft delete).

        Args:
            grader_id: UUID of the grader to delete.

        Raises:
            WatcherNotFoundError: If no grader exists with the given ID.
        """
        return await _delete_grader_api.asyncio_detailed(grader_id, client=self._generated_client)  # pyright: ignore[reportReturnType]  # ty: ignore[invalid-return-type]

    @_sdk_method
    async def search_graders(
        self,
        query: str,
        limit: int = 100,
        offset: int = 0,
    ) -> GraderSearchResponse:
        """Search graders by name and header/footer content.

        Args:
            query: Search query string.
            limit: Maximum number of graders to return per page.
            offset: Number of graders to skip (for pagination).

        Returns:
            GraderSearchResponse containing matched graders and total count.
        """
        body = GraderSearchRequest(query=query, limit=limit, offset=offset)
        return await _search_graders_api.asyncio_detailed(client=self._generated_client, body=body)  # pyright: ignore[reportReturnType]  # ty: ignore[invalid-return-type]

    @_sdk_method
    async def list_grader_models(self) -> ModelsConfig:
        """Return the configured grader model allowlist and frontend suggestions.

        Echoes the active server config's ``models`` section: ``suggested``
        models tagged for UI locations (``triage``, ``gateway``,
        ``grader_default``) plus ``enabled`` fnmatch patterns enforced on
        ``Grader.default_model``.
        """
        return await _list_grader_models_api.asyncio_detailed(client=self._generated_client)  # pyright: ignore[reportReturnType]  # ty: ignore[invalid-return-type]

    # ---- Sessions ----

    @_sdk_method
    async def list_sessions(
        self,
        limit: int = 100,
        offset: int = 0,
        sort_by: str = "ended_at",
        sort_order: str = "desc",
    ) -> SessionListResponse:
        """List sessions with pagination and sorting.

        Args:
            limit: Maximum number of sessions to return per page.
            offset: Number of sessions to skip (for pagination).
            sort_by: Field to sort by ('ended_at' or 'started_at').
            sort_order: Sort direction ('asc' or 'desc').

        Returns:
            SessionListResponse containing the page of sessions and the total
            count for pagination.
        """
        return await _list_sessions_api.asyncio_detailed(  # pyright: ignore[reportReturnType]  # ty: ignore[invalid-return-type]
            client=self._generated_client, limit=limit, offset=offset, sort_by=sort_by, sort_order=sort_order
        )

    @_sdk_method
    async def search_sessions(
        self,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        external_ids: dict[str, list[str]] | None = None,
        agent_platforms: list[str] | None = None,
        grading_statuses: list[str] | None = None,
        categories: list[str] | None = None,
        severities: list[str] | None = None,
        limit: int = 100,
        offset: int = 0,
        sort_by: str = "ended_at",
        sort_order: str = "desc",
        session_id: str | None = None,
        session_id_contains: str | None = None,
        session_name_contains: str | None = None,
        *,
        users: UserFilter | None = None,
        sources: list[str] | None = None,
    ) -> SessionListResponse:
        """Search sessions with filtering, pagination, and sorting.

        Sessions with no messages never match, regardless of filters.

        Args:
            start_date: Include only sessions with activity at or after this datetime.
                A session's recorded span runs from its first through its latest
                message, so a session still in progress matches if it has had
                activity at or after this time.
            end_date: Include only sessions that started on or before this datetime.
            external_ids: Filter by external ID mappings. Keys are namespace strings,
                values are lists of IDs to match within that namespace. Example:
                {"anthropic-claude-code": ["cc-123", "cc-456"], "tailscale-aperture": ["ancc_789"]}
            agent_platforms: Filter by agent platforms. Known values: 'claude_code', 'codex',
                'opencode', 'gemini_cli', 'antigravity_cli', 'qwen_code', 'mistral_vibe', 'pi' and
                'other'; any string is accepted and unknown values match no sessions.
            grading_statuses: Filter by derived grading status.
            categories: Filter by score category names.
            severities: Filter by exact severity buckets.
            limit: Maximum number of sessions to return per page.
            offset: Number of sessions to skip (for pagination).
            sort_by: Field to sort by ('ended_at' or 'started_at').
            sort_order: Sort direction ('asc' or 'desc').
            session_id: Filter by exact Watcher session ID.
            session_id_contains: Case-insensitive substring match against the session ID.
            session_name_contains: Case-insensitive substring match against the graded
                session name. Does not match the session owner's name or email; use
                users to filter by owner.
            users: Owner selection with nonempty UUID ids and an explicit
                UserFilterMode.INCLUDE or EXCLUDE. Include matches any listed owner;
                exclude removes all listed owners and retains unattributed sessions.
                None selects all owners allowed by your read scope. Naming another
                user requires sessions:findings:read:any in either mode; otherwise the server
                returns 403. An empty ids list is rejected with 422.
            sources: Match any listed ingestion source among the session's retained
                messages. Known values are 'watcher', 'tailscale-aperture',
                'watcher-gateway', 'watcher-sdk' and 'watcher-hook'; the last
                three split hook messages by the session's conversation-ID
                prefix. Custom source strings are accepted. None omits this
                filter. An empty list is rejected with 422.

        Returns:
            SessionListResponse containing matched sessions and total count.
        """
        external_ids_model = (
            SessionSearchFiltersExternalIdsType0.from_dict(external_ids) if external_ids is not None else None
        )
        filters = SessionSearchFilters(
            start_date=start_date,
            end_date=end_date,
            session_id=UUID(session_id) if session_id is not None else None,
            external_ids=external_ids_model,
            agent_platforms=agent_platforms,
            grading_statuses=(
                [SessionSearchFiltersGradingStatusesType0Item(s) for s in grading_statuses]
                if grading_statuses is not None
                else None
            ),
            categories=categories,
            severities=(
                [SessionSearchFiltersSeveritiesType0Item(severity) for severity in severities]
                if severities is not None
                else None
            ),
            session_id_contains=session_id_contains,
            session_name_contains=session_name_contains,
            users=users,
            sources=sources if sources is not None else UNSET,
        )
        body = SessionSearchParams(
            limit=limit,
            offset=offset,
            sort_by=SessionSearchParamsSortBy(sort_by),
            sort_order=SessionSearchParamsSortOrder(sort_order),
            filters=filters,
        )
        return await _search_sessions_api.asyncio_detailed(client=self._generated_client, body=body)  # pyright: ignore[reportReturnType]  # ty: ignore[invalid-return-type]

    @_sdk_method
    async def search_tool_calls(
        self,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        session_id: str | UUID | None = None,
        user_id: str | UUID | None = None,
        tool_names: list[str] | None = None,
        severities: list[str] | None = None,
        decision_categories: list[str] | None = None,
        limit: int = 50,
        offset: int = 0,
        sort_by: str = "severity",
        sort_order: str = "desc",
        *,
        is_flagged: bool | None = None,
        trajectory_id: str | None = None,
    ) -> ToolCallListResponse:
        """Search tool calls with filtering, pagination, and sorting.

        Lists one row per tool call Watcher recorded a decision about, the same
        population the dashboard's tool-call counts are computed over. Retained
        verdict-only rows remain after session content is scrubbed; their
        ``content_state`` is ``"scrubbed"`` and they omit live tool details.
        Calls that never reached Watcher's decision path are not returned.

        Args:
            start_date: Include only calls whose message was recorded at or after this
                datetime. Calls are dated by their own message rather than by their
                session's span.
            end_date: Include only calls whose message was recorded at or before this datetime.
            session_id: Restrict to one session's calls.
            user_id: Restrict to one person's calls. Callers without the
                ``sessions:findings:read:any`` permission may only name themselves.
            tool_names: Restrict to these tool names. Any string is accepted and an
                unknown name matches no calls. Scrubbed calls cannot match because
                tool names are not retained.
            severities: Score bands to keep ('critical', 'high', 'medium', 'low'), plus
                'not_scored' for calls with no usable gateway or triage score. Inspect
                coverage_state to distinguish unscored decisions from pipeline gaps.
            decision_categories: Permission-decision values to keep: 'human_denied',
                'auto_denied', 'human_allowed', 'would_denied', 'would_escalated', plus
                'cleared' for calls Watcher allowed without asking. Routine calls match
                none of them.
            is_flagged: Filter by recorded risk, including observe-mode judgments.
            trajectory_id: Restrict to this trajectory and its ancestors, or ``latest``.
                Requires ``session_id``. Missing or scrubbed trajectories match no calls.
            limit: Maximum number of calls to return per page.
            offset: Number of calls to skip (for pagination).
            sort_by: Field to sort by: 'severity', 'decision' (interventions first),
                'occurred_at' or 'tool_name'.
            sort_order: Sort direction ('asc' or 'desc').

        Returns:
            ToolCallListResponse containing matched tool calls and total count.
        """
        filters = ToolCallSearchFilters(
            is_flagged=is_flagged,
            trajectory_id=trajectory_id,
            start_date=start_date,
            end_date=end_date,
            session_id=UUID(session_id) if isinstance(session_id, str) else session_id,
            user_id=UUID(user_id) if isinstance(user_id, str) else user_id,
            tool_names=tool_names,
            severities=(
                [ToolCallSearchFiltersSeveritiesType0Item(severity) for severity in severities]
                if severities is not None
                else None
            ),
            decision_categories=(
                [ToolCallSearchFiltersDecisionCategoriesType0Item(category) for category in decision_categories]
                if decision_categories is not None
                else None
            ),
        )
        body = ToolCallSearchParams(
            limit=limit,
            offset=offset,
            sort_by=ToolCallSearchParamsSortBy(sort_by),
            sort_order=ToolCallSearchParamsSortOrder(sort_order),
            filters=filters,
        )
        return await _search_tool_calls_api.asyncio_detailed(client=self._generated_client, body=body)  # pyright: ignore[reportReturnType]  # ty: ignore[invalid-return-type]

    @_sdk_method
    async def get_session_aggregates(
        self,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        bucket: str = "day",
        user_id: str | UUID | None = None,
        *,
        severity_threshold: str,
    ) -> SessionAggregatesResponse:
        """Get organization aggregate metrics, optionally filtered by ``user_id``.

        Requires ``sessions:aggregates:read:any``, even for the caller's own metrics.
        """
        return await _session_aggregates_api.asyncio_detailed(  # pyright: ignore[reportReturnType]  # ty: ignore[invalid-return-type]
            client=self._generated_client,
            start_date=start_date,
            end_date=end_date,
            bucket=GetSessionAggregatesEndpointV1SessionsAggregatesGetBucket(bucket),
            severity_threshold=GetSessionAggregatesEndpointV1SessionsAggregatesGetSeverityThreshold(severity_threshold),
            user_id=UUID(user_id) if isinstance(user_id, str) else user_id,
        )

    @_sdk_method
    async def get_org_managed_settings(self, path: str = "settings.yaml") -> OrgManagedSettingsDoc:
        """Get the organization's current managed settings document for a path."""
        return await _get_org_managed_settings_api.asyncio_detailed(path, client=self._generated_client)  # pyright: ignore[reportReturnType]  # ty: ignore[invalid-return-type]

    @_sdk_method
    async def update_org_managed_settings(
        self, yaml: str, *, expected_version: int, path: str = "settings.yaml"
    ) -> OrgManagedSettingsDoc:
        """Validate and save a new organization managed settings version.

        Args:
            yaml: Complete managed settings YAML document.
            expected_version: Version returned by ``get_org_managed_settings``.
            path: Managed settings file path; phase-1 serves only ``settings.yaml``.

        Raises:
            WatcherValidationError: When the document or request is invalid.
            WatcherAPIError: When the expected version is stale or the caller
                lacks permission to update settings.
        """
        body = OrgManagedSettingsUpdate(yaml=yaml, expected_version=expected_version)
        return await _update_org_managed_settings_api.asyncio_detailed(  # pyright: ignore[reportReturnType]  # ty: ignore[invalid-return-type]
            path,
            client=self._generated_client,
            body=body,
        )

    @_sdk_method(postprocess=lambda r: r.to_dict())
    async def get_org_managed_settings_schema(self, path: str = "settings.yaml") -> dict[str, Any]:
        """Get the JSON Schema of the managed settings document, for editor hints."""
        return await _get_org_managed_settings_schema_api.asyncio_detailed(  # pyright: ignore[reportReturnType]  # ty: ignore[invalid-return-type]
            path, client=self._generated_client
        )

    @_sdk_method
    async def resolve_org_managed_settings(self, path: str = "settings.yaml") -> OrgManagedSettingsResolved:
        """Get the org's managed settings document as machines should apply it.

        Returns the YAML document machines should write to their org settings
        layer, plus its version for change detection.

        Raises:
            WatcherNotFoundError: When the org does not distribute settings via
                Watcher (distribution is MDM), when no document has been saved
                yet, or when the server predates this endpoint. Callers treat
                all of these as "no managed settings" and keep their
                last-known-good file. The first two are the server's expected
                404 and carry ``code == "no_managed_settings"`` (proof the
                request authenticated, since only the post-auth route handler
                emits it); the older-server routing 404 has ``code is None``.
        """
        return await _resolve_org_managed_settings_api.asyncio_detailed(path, client=self._generated_client)  # pyright: ignore[reportReturnType]  # ty: ignore[invalid-return-type]

    @_sdk_method
    async def get_org_managed_settings_monitors(self, path: str = "settings.yaml") -> ActivatedMonitorsResponse:
        """Get which graders the current managed settings document activates, by stage."""
        return await _get_org_managed_settings_monitors_api.asyncio_detailed(  # pyright: ignore[reportReturnType]  # ty: ignore[invalid-return-type]
            path, client=self._generated_client
        )

    @_sdk_method
    async def get_monitor_customization(self) -> MonitorCustomizationResponse:
        """Get the org's monitor customization (empty instructions when never set)."""
        return await _get_monitor_customization_api.asyncio_detailed(client=self._generated_client)  # pyright: ignore[reportReturnType]  # ty: ignore[invalid-return-type]

    @_sdk_method
    async def update_monitor_customization(self, instructions: str) -> MonitorCustomizationResponse:
        """Set the org's monitor customization (an empty instructions string clears it).

        The instructions are injected into every server-managed monitor's
        prompt as organization policy. Requires ``org:settings:write``.

        Raises:
            WatcherValidationError: When the text exceeds the length cap or
                contains a reserved delimiter sequence.
        """
        body = UpdateMonitorCustomizationRequest(instructions=instructions)
        return await _update_monitor_customization_api.asyncio_detailed(  # pyright: ignore[reportReturnType]  # ty: ignore[invalid-return-type]
            client=self._generated_client, body=body
        )

    @_sdk_method
    async def get_grading_usage(
        self,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        bucket: str = "day",
        kind: str = "all",
        user_id: str | UUID | None = None,
        model: str | None = None,
        grader_id: str | UUID | None = None,
    ) -> GradingUsageResponse:
        """Get grading usage aggregates (admin-only).

        Returns trailing/live grading request counts (and token totals when
        the deployment exposes them) as a by-date series plus window totals
        per user, model, and grader.
        """
        return await _grading_usage_api.asyncio_detailed(  # pyright: ignore[reportReturnType]  # ty: ignore[invalid-return-type]
            client=self._generated_client,
            start_date=start_date,
            end_date=end_date,
            bucket=GetGradingUsageEndpointV1UsageGradingGetBucket(bucket),
            kind=GetGradingUsageEndpointV1UsageGradingGetKind(kind),
            user_id=UUID(user_id) if isinstance(user_id, str) else user_id,
            model=model,
            grader_id=UUID(grader_id) if isinstance(grader_id, str) else grader_id,
        )

    @_sdk_method
    async def get_usage_limits(self) -> UsageLimitsResponse:
        """Get this month's grading limit status for the org (admin-only).

        Reports whether grading is currently stopped, when the period resets,
        and the grader calls used against the org's call limit — ``call_limit``
        is ``None`` when the org is uncapped.
        """
        return await _usage_limits_api.asyncio_detailed(client=self._generated_client)  # pyright: ignore[reportReturnType]  # ty: ignore[invalid-return-type]

    @_sdk_method
    async def get_session_filter_options(self) -> SessionFilterOptionsResponse:
        """Return category filter options for session search."""
        return await _get_session_filter_options_api.asyncio_detailed(client=self._generated_client)  # pyright: ignore[reportReturnType]  # ty: ignore[invalid-return-type]

    @_sdk_method
    async def get_session(self, session_id: str) -> SessionDetailResponse:
        """Get available trajectory detail or a scrubbed session summary.

        Args:
            session_id: Unique identifier of the session to retrieve.

        Returns:
            AvailableSessionDetailResponse when content exists, otherwise
            ScrubbedSessionDetailResponse with retained session grades.

        Raises:
            WatcherNotFoundError: If no session exists with the given ID.
        """
        return await _get_session_api.asyncio_detailed(session_id, client=self._generated_client)  # pyright: ignore[reportReturnType]  # ty: ignore[invalid-return-type]

    @_sdk_method
    async def get_session_tool_call_decision(self, session_id: str, tool_use_id: str) -> ToolCallFindingsResponse:
        """Get one tool call's decision and grades with session findings access.

        ``has_result`` reports whether a tool response was recorded; its contents,
        raw tool arguments and grader input messages are always omitted. Use
        ``get_trajectory`` with content access to retrieve transcript evidence.

        Args:
            session_id: Unique identifier of the session.
            tool_use_id: Tool-call identifier, including any subagent prefix.

        Raises:
            WatcherNotFoundError: If the decision is missing, scrubbed, or the
                caller cannot read the session's findings.
        """
        return await _get_tool_call_decision_api.asyncio_detailed(  # pyright: ignore[reportReturnType]  # ty: ignore[invalid-return-type]
            session_id, client=self._generated_client, tool_use_id=tool_use_id
        )

    @_sdk_method
    async def get_session_tool_call(self, session_id: str, tool_use_id: str) -> ToolCallDetailResponse:
        """Read one call's permitted arguments, result and optional decision.

        Findings and content are authorized independently. Access flags distinguish
        restricted fields from missing data, including calls with no grading record.
        Surrounding messages and grader input transcripts are never returned.

        Args:
            session_id: Session UUID.
            tool_use_id: Exact tool-use ID, including any nested-call suffix.

        Raises:
            WatcherNotFoundError: If the session is inaccessible or scrubbed, or the
                call does not exist in that session.
            WatcherValidationError: If the session UUID is malformed or tool_use_id is empty.
        """
        return await _get_tool_call_api.asyncio_detailed(  # pyright: ignore[reportReturnType]  # ty: ignore[invalid-return-type]
            session_id, client=self._generated_client, tool_use_id=tool_use_id
        )

    @_sdk_method
    async def scrub_session_content(self, session_id: str) -> None:
        """Remove stored content for a session while retaining its historical record.

        Args:
            session_id: Unique identifier of the session to scrub.

        Raises:
            WatcherNotFoundError: If no visible session exists with the given ID.
            WatcherForbiddenError: If the caller cannot scrub session content.
        """
        return await _scrub_session_content_api.asyncio_detailed(  # pyright: ignore[reportReturnType]  # ty: ignore[invalid-return-type]
            session_id, client=self._generated_client
        )

    @_sdk_method
    async def request_deep_review(self, session_id: str) -> DeepReviewRequestResponse:
        """Queue a deep review of a session's latest transcript, or return the one already queued.

        Poll ``get_deep_review_request`` until the status is ``succeeded`` or
        ``failed``; the report then appears among the session's grades.

        Args:
            session_id: Unique identifier of the session to review.

        Returns:
            The review's operation ID and status. Repeating the request for an
            unchanged transcript returns the same operation.

        Raises:
            WatcherNotFoundError: If the caller cannot grade this session.
            WatcherAPIError: With status 409 if the session has nothing to
                review or a review cannot be started for it; 402 if the
                organization is over its grading cap.
        """
        return await _request_deep_review_api.asyncio_detailed(session_id, client=self._generated_client)  # pyright: ignore[reportReturnType]  # ty: ignore[invalid-return-type]

    @_sdk_method
    async def get_deep_review_request(self, session_id: str, operation_id: str) -> DeepReviewRequestResponse:
        """Get the status of a deep review queued by ``request_deep_review``.

        Args:
            session_id: Unique identifier of the reviewed session.
            operation_id: Operation ID returned when the review was requested.

        Raises:
            WatcherNotFoundError: If the session is not visible or the operation
                is not this session's review.
        """
        return await _get_deep_review_request_api.asyncio_detailed(  # pyright: ignore[reportReturnType]  # ty: ignore[invalid-return-type]
            session_id, UUID(operation_id), client=self._generated_client
        )

    @_sdk_method
    async def get_current_deep_review(self, session_id: str) -> SessionDeepReviewResponse:
        """Get the deep review a viewer of this session should see, however it was queued.

        Returns an unfinished review if one exists, otherwise the latest review
        of the session's current transcript. ``current`` is None when no review
        was requested for it.

        Args:
            session_id: Unique identifier of the session.

        Raises:
            WatcherNotFoundError: If the session is not visible.
        """
        return await _get_current_deep_review_api.asyncio_detailed(session_id, client=self._generated_client)  # pyright: ignore[reportReturnType]  # ty: ignore[invalid-return-type]

    # ---- Trajectories ----

    @_sdk_method
    async def list_trajectories(self, session_id: str) -> TrajectoryListInSessionResponse:
        """List all trajectories in a session.

        Args:
            session_id: Unique identifier of the session.

        Returns:
            TrajectoryListInSessionResponse containing summary information
            for each trajectory in the session.

        Raises:
            WatcherNotFoundError: If no session exists with the given ID.
        """
        return await _list_trajectories_api.asyncio_detailed(session_id, client=self._generated_client)  # pyright: ignore[reportReturnType]  # ty: ignore[invalid-return-type]

    @_sdk_method
    async def get_trajectory(
        self, session_id: str, trajectory_id: str, view: TrajectoryView = TrajectoryView.TRUNCATED
    ) -> TrajectoryDetailResponse:
        """Get full trajectory detail within a session.

        Args:
            session_id: Unique identifier of the session.
            trajectory_id: Unique identifier of the trajectory within the session.
            view: Payload shape — defaults to ``TrajectoryView.TRUNCATED``, the
                display view with heavy payloads elided behind marker fields.
                Pass ``TrajectoryView.EXTENDED`` explicitly when you need
                storage-faithful message content.

        Returns:
            TrajectoryDetailResponse with the trajectory data including messages
            and any associated grades.

        Raises:
            WatcherNotFoundError: If the session or trajectory does not exist.
        """
        return await _get_trajectory_api.asyncio_detailed(  # pyright: ignore[reportReturnType]  # ty: ignore[invalid-return-type]
            session_id, trajectory_id, client=self._generated_client, view=view
        )

    @_sdk_method
    async def get_message(self, session_id: str, message_ref: str) -> MessageDetailResponse:
        """Get one message's full stored content by its ``message_ref``.

        Trajectory-response messages carry a ``message_ref`` (the message's own
        chain hash); this fetches that single message with full content, so
        expanding one elided item never refetches the whole trajectory.

        Args:
            session_id: Unique identifier of the session.
            message_ref: The message's ``message_ref`` from a trajectory response.

        Returns:
            MessageDetailResponse with the single full-content message.

        Raises:
            WatcherNotFoundError: If the session or message does not exist.
        """
        return await _get_message_api.asyncio_detailed(  # pyright: ignore[reportReturnType]  # ty: ignore[invalid-return-type]
            session_id, message_ref, client=self._generated_client
        )

    # ---- Users ----

    @_sdk_method
    async def list_my_session_content_access_requests(
        self,
        *,
        session_id: UUID | None = None,
        status: SessionContentAccessRequestStatus | None = None,
        active_only: bool = False,
        limit: int = 20,
        offset: int = 0,
    ) -> SessionContentAccessRequestListResponse:
        """List the signed-in user's requests in their current organization.

        Results are newest first. The optional status filter matches the stored
        decision; approved requests include expired approvals. Credentials must
        identify a user, including when the caller has the admin role.
        ``active_only`` includes only pending requests and currently valid approvals.
        """
        return await _list_my_content_access_requests_api.asyncio_detailed(  # pyright: ignore[reportReturnType]  # ty: ignore[invalid-return-type]
            client=self._generated_client,
            session_id=session_id,
            status=status,
            active_only=active_only,
            limit=limit,
            offset=offset,
        )

    @_sdk_method
    async def request_session_content_access(self, session_id: UUID) -> SessionContentAccessRequestSummary:
        """Request temporary content access; return the existing request when already pending.

        Requires a user identity. Missing, foreign, or scrubbed sessions return
        404; content the caller can already read returns 409.
        """
        return await _create_my_content_access_request_api.asyncio_detailed(  # pyright: ignore[reportReturnType]  # ty: ignore[invalid-return-type]
            client=self._generated_client, body=CreateSessionContentAccessRequest(session_id=session_id)
        )

    @_sdk_method
    async def list_session_content_access_requests(
        self,
        *,
        status: list[SessionContentAccessRequestStatus] | None = None,
        view: SessionContentAccessRequestView | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> AdminSessionContentAccessRequestListResponse:
        """List organization requests with requester, reviewer, and revoker identities.

        Requires ``sessions:access-requests:review``, included in the admin role.
        Filter by stored statuses and/or a pending, active, or historical view.
        Approved status includes expired approvals; active view excludes them.
        Pending/active counts always cover the organization, regardless of filters.
        """
        return await _list_content_access_requests_api.asyncio_detailed(  # pyright: ignore[reportReturnType]  # ty: ignore[invalid-return-type]
            client=self._generated_client, status=status, view=view, limit=limit, offset=offset
        )

    @_sdk_method
    async def review_session_content_access_request(
        self, request_id: UUID, body: ReviewSessionContentAccessRequest
    ) -> SessionContentAccessRequestSummary:
        """Approve or deny a pending request as a signed-in reviewer.

        Requires ``sessions:access-requests:review``, included in the admin role.
        Self-approval is allowed and recorded. Approvals default to eight hours;
        an explicit expiry must be in the future and within eight hours of review.
        Review decisions cannot be replaced; active approvals can be revoked separately.
        """
        return await _review_content_access_request_api.asyncio_detailed(  # pyright: ignore[reportReturnType]  # ty: ignore[invalid-return-type]
            request_id=request_id, client=self._generated_client, body=body
        )

    @_sdk_method
    async def revoke_session_content_access_request(self, request_id: UUID) -> SessionContentAccessRequestSummary:
        """Revoke an active approval, preserving its original review and expiry.

        Requires ``sessions:access-requests:review`` and a signed-in user identity.
        Missing or foreign requests return 404; requests without an active approval
        return 409, including repeat revocations.
        """
        return await _revoke_content_access_request_api.asyncio_detailed(  # pyright: ignore[reportReturnType]  # ty: ignore[invalid-return-type]
            request_id=request_id, client=self._generated_client
        )

    @_sdk_method
    async def list_users(self, limit: int = 100, offset: int = 0) -> UserListResponse:
        """List users that are members of the authenticated organization."""
        return await _list_users_api.asyncio_detailed(  # pyright: ignore[reportReturnType]  # ty: ignore[invalid-return-type]
            client=self._generated_client, limit=limit, offset=offset
        )

    @_sdk_method
    async def get_user(self, user_id: str) -> UserSummary:
        """Fetch a user by id, scoped to the authenticated organization."""
        return await _get_user_api.asyncio_detailed(user_id, client=self._generated_client)  # pyright: ignore[reportReturnType]  # ty: ignore[invalid-return-type]

    @_sdk_method
    async def get_me(self) -> UserSummary:
        """Return the authenticated user's profile (requires JWT auth)."""
        return await _users_me_api.asyncio_detailed(client=self._generated_client)  # pyright: ignore[reportReturnType]  # ty: ignore[invalid-return-type]

    # ---- Health ----

    @_sdk_method
    async def health(self) -> HealthResponse:
        """Check whether the Watcher API server is running.

        Returns:
            HealthResponse indicating the server is alive.
        """
        return await _health_api.asyncio_detailed(client=self._generated_client)  # pyright: ignore[reportReturnType]  # ty: ignore[invalid-return-type]

    @_sdk_method
    async def version(self) -> VersionResponse:
        """Return the build stamped into the connected Watcher deployment.

        Returns:
            VersionResponse with version and git_sha ("dev"/None when unstamped).
        """
        return await _version_api.asyncio_detailed(client=self._generated_client)  # pyright: ignore[reportReturnType]  # ty: ignore[invalid-return-type]

    # ---- Convenience ----

    async def ingest_and_grade(
        self,
        source: str,
        trajectories: list[ClaudeCodeTrajectory | CodexTrajectory | CopilotTrajectory | ApertureLog],
        grader_ids: list[str],
    ) -> tuple[IngestResponse, GradeResponse]:
        """Ingest trajectories and immediately grade them.

        Convenience method that calls ingest() then grade() in sequence,
        passing the session_id and trajectory_ids from the ingest response
        directly into the grade call.

        Args:
            source: Identifier for the data source (e.g. pipeline name or tool name).
            trajectories: List of trajectories to ingest.
            grader_ids: Grader IDs to run. Required — the server has no
                default grader, and rejects a grade request without it (422).

        Returns:
            A (IngestResponse, GradeResponse) tuple with results from both steps.
        """
        ingest_resp = await self.ingest(source, trajectories)
        grade_resp = await self.grade(
            session_id=ingest_resp.session_id,
            trajectory_ids=ingest_resp.trajectory_ids,
            grader_ids=grader_ids,
        )
        return ingest_resp, grade_resp

    # ---- Pagination iterators ----

    def list_sessions_iter(
        self,
        page_size: int = 100,
        sort_by: str = "ended_at",
        sort_order: str = "desc",
    ) -> AsyncIterator[SessionSummary]:
        """Iterate over all sessions, auto-paginating.

        Returns an async iterator that fetches pages on demand. Each page makes
        one HTTP request to list_sessions.

        Args:
            page_size: Number of sessions per page.
            sort_by: Field to sort by ('ended_at' or 'started_at').
            sort_order: Sort direction ('asc' or 'desc').

        Returns:
            AsyncIterator yielding individual SessionSummary objects across all pages.
        """
        return PaginatedIterator(
            fetch_page=lambda offset: self.list_sessions(
                limit=page_size, offset=offset, sort_by=sort_by, sort_order=sort_order
            ),
            page_size=page_size,
        )

    def search_sessions_iter(
        self,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        external_ids: dict[str, list[str]] | None = None,
        agent_platforms: list[str] | None = None,
        grading_statuses: list[str] | None = None,
        categories: list[str] | None = None,
        severities: list[str] | None = None,
        page_size: int = 100,
        sort_by: str = "ended_at",
        sort_order: str = "desc",
        session_id: str | None = None,
        session_id_contains: str | None = None,
        session_name_contains: str | None = None,
        *,
        users: UserFilter | None = None,
        sources: list[str] | None = None,
    ) -> AsyncIterator[SessionSummary]:
        """Iterate over search results, auto-paginating.

        Returns an async iterator that fetches pages on demand. Each page makes
        one HTTP request to search_sessions with the given filters. Sessions
        with no messages never match, regardless of filters.

        Args:
            start_date: Include only sessions with activity at or after this datetime.
                A session's recorded span runs from its first through its latest
                message, so a session still in progress matches if it has had
                activity at or after this time.
            end_date: Include only sessions that started on or before this datetime.
            external_ids: Filter by external ID mappings. Keys are namespace strings,
                values are lists of IDs to match within that namespace.
            agent_platforms: Filter by agent platforms. Known values: 'claude_code', 'codex',
                'opencode', 'gemini_cli', 'antigravity_cli', 'qwen_code', 'mistral_vibe', 'pi' and
                'other'; any string is accepted and unknown values match no sessions.
            grading_statuses: Filter by derived grading status.
            categories: Filter by score category names.
            severities: Filter by exact severity buckets.
            page_size: Number of sessions per page.
            sort_by: Field to sort by.
            sort_order: Sort direction ('asc' or 'desc').
            session_id: Filter by exact Watcher session ID.
            session_id_contains: Case-insensitive substring match against the session ID.
            session_name_contains: Case-insensitive substring match against the graded
                session name. Does not match the session owner's name or email.
            users: Owner selection, forwarded on every page. See search_sessions
                for include/exclude semantics, validation, and required permissions.
            sources: Ingestion sources to match, forwarded on every page. See
                search_sessions for retained-message and selection semantics.

        Returns:
            AsyncIterator yielding individual SessionSummary objects across all pages.
        """
        return SearchPaginatedIterator(
            fetch_page=lambda offset: self.search_sessions(
                start_date=start_date,
                end_date=end_date,
                external_ids=external_ids,
                agent_platforms=agent_platforms,
                grading_statuses=grading_statuses,
                categories=categories,
                severities=severities,
                limit=page_size,
                offset=offset,
                sort_by=sort_by,
                sort_order=sort_order,
                session_id=session_id,
                session_id_contains=session_id_contains,
                session_name_contains=session_name_contains,
                users=users,
                sources=sources,
            ),
            page_size=page_size,
        )

    # ---- Context manager ----

    async def __aenter__(self) -> Self:
        """Enter async context manager.

        When ``_sdk_manages_httpx_lifecycle`` is False (caller opted out for a shared
        injected httpx client), we skip the generated client's context so the httpx
        owner can outlive this SDK wrapper.
        """
        if self._sdk_manages_httpx_lifecycle:
            await self._generated_client.__aenter__()
        return self

    async def __aexit__(self, *args: object) -> None:
        """Exit async context manager when the SDK owns httpx teardown."""
        if self._sdk_manages_httpx_lifecycle:
            await self._generated_client.__aexit__(*args)
