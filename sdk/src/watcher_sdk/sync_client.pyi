"""Type stubs for WatcherClient — provides IDE autocomplete and type checking.

These signatures mirror AsyncWatcherClient exactly (minus async/await).
Methods are auto-delegated at runtime via __getattr__; these stubs exist
solely for static analysis tools.
"""

from collections.abc import Iterator, Mapping, Sequence
from datetime import datetime
from typing import Any, Self, overload
from uuid import UUID

import anyio.from_thread
import httpx

from watcher_sdk._generated.models.activated_monitors_response import ActivatedMonitorsResponse
from watcher_sdk._generated.models.admin_session_content_access_request_list_response import (
    AdminSessionContentAccessRequestListResponse,
)
from watcher_sdk._generated.models.agent_relationship_request import AgentRelationshipRequest
from watcher_sdk._generated.models.agent_relationship_response import AgentRelationshipResponse
from watcher_sdk._generated.models.aperture_hook_accepted import ApertureHookAccepted
from watcher_sdk._generated.models.aperture_log import ApertureLog
from watcher_sdk._generated.models.auth_client_config import AuthClientConfig
from watcher_sdk._generated.models.claude_code_trajectory import ClaudeCodeTrajectory
from watcher_sdk._generated.models.codex_trajectory import CodexTrajectory
from watcher_sdk._generated.models.copilot_trajectory import CopilotTrajectory
from watcher_sdk._generated.models.deep_review_request_response import DeepReviewRequestResponse
from watcher_sdk._generated.models.device_authorization_response import DeviceAuthorizationResponse
from watcher_sdk._generated.models.device_token_response import DeviceTokenResponse
from watcher_sdk._generated.models.grade_response import GradeResponse
from watcher_sdk._generated.models.grader_detail import GraderDetail
from watcher_sdk._generated.models.grader_list_response import GraderListResponse
from watcher_sdk._generated.models.grader_search_response import GraderSearchResponse
from watcher_sdk._generated.models.grading_usage_response import GradingUsageResponse
from watcher_sdk._generated.models.health_response import HealthResponse
from watcher_sdk._generated.models.hook_append_response import HookAppendResponse
from watcher_sdk._generated.models.hook_call_error import HookCallError
from watcher_sdk._generated.models.ingest_response import IngestResponse
from watcher_sdk._generated.models.message_detail_response import MessageDetailResponse
from watcher_sdk._generated.models.models_config import ModelsConfig
from watcher_sdk._generated.models.monitor_customization_response import MonitorCustomizationResponse
from watcher_sdk._generated.models.monitors_response import MonitorsResponse
from watcher_sdk._generated.models.org_managed_settings_doc import OrgManagedSettingsDoc
from watcher_sdk._generated.models.org_managed_settings_resolved import OrgManagedSettingsResolved
from watcher_sdk._generated.models.permission_check_response import PermissionCheckResponse
from watcher_sdk._generated.models.pre_tool_use_hook_response import PreToolUseHookResponse
from watcher_sdk._generated.models.review_session_content_access_request import ReviewSessionContentAccessRequest
from watcher_sdk._generated.models.session_aggregates_response import SessionAggregatesResponse
from watcher_sdk._generated.models.session_content_access_request_list_response import (
    SessionContentAccessRequestListResponse,
)
from watcher_sdk._generated.models.session_content_access_request_status import SessionContentAccessRequestStatus
from watcher_sdk._generated.models.session_content_access_request_summary import SessionContentAccessRequestSummary
from watcher_sdk._generated.models.session_content_access_request_view import SessionContentAccessRequestView
from watcher_sdk._generated.models.session_deep_review_response import SessionDeepReviewResponse
from watcher_sdk._generated.models.session_filter_options_response import SessionFilterOptionsResponse
from watcher_sdk._generated.models.session_list_response import SessionListResponse
from watcher_sdk._generated.models.session_summary import SessionSummary
from watcher_sdk._generated.models.subagent_list_response import SubagentListResponse
from watcher_sdk._generated.models.tool_call_detail_response import ToolCallDetailResponse
from watcher_sdk._generated.models.tool_call_findings_response import ToolCallFindingsResponse
from watcher_sdk._generated.models.tool_call_list_response import ToolCallListResponse
from watcher_sdk._generated.models.trajectory_detail_response import TrajectoryDetailResponse
from watcher_sdk._generated.models.trajectory_list_in_session_response import TrajectoryListInSessionResponse
from watcher_sdk._generated.models.trajectory_view import TrajectoryView
from watcher_sdk._generated.models.usage_limits_response import UsageLimitsResponse
from watcher_sdk._generated.models.user_filter import UserFilter
from watcher_sdk._generated.models.user_list_response import UserListResponse
from watcher_sdk._generated.models.user_profile import UserProfile
from watcher_sdk._generated.models.user_summary import UserSummary
from watcher_sdk._generated.models.version_response import VersionResponse
from watcher_sdk.auth_support import AuthExchangeResult, AuthLogoutResult
from watcher_sdk.client import (
    AsyncWatcherClient,
    ChatMessage,
    LocalPreToolUseDecision,
    SessionDetailResponse,
    _HookInputMapping,
)

class WatcherClient:
    _async_client: AsyncWatcherClient
    _portal: anyio.from_thread.BlockingPortal | None
    _portal_cm: object | None

    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        api_key: str | None = None,
        access_token: str | None = None,
        timeout: float = 30.0,
        max_retries: int = 3,
        httpx_client: httpx.AsyncClient | None = None,
        manage_external_httpx_client_lifecycle: bool = True,
    ) -> None: ...
    def _run(self, coro: Any) -> Any: ...
    def open(self) -> None: ...
    def close(self) -> None: ...
    def __enter__(self) -> Self: ...
    def __exit__(self, *args: object) -> None: ...
    def __getattr__(self, name: str) -> Any: ...

    # ---- API methods (auto-delegated to AsyncWatcherClient) ----

    def auth_callback(self, code: str) -> AuthExchangeResult: ...
    def auth_refresh(
        self,
        *,
        refresh_token: str | None = None,
        organization_id: str | None = None,
    ) -> AuthExchangeResult: ...
    def auth_logout(self) -> AuthLogoutResult: ...
    def auth_me(self) -> UserProfile: ...
    def auth_client_config(self) -> AuthClientConfig: ...
    def auth_device_authorize(self) -> DeviceAuthorizationResponse: ...
    def auth_device_token(self, device_code: str) -> DeviceTokenResponse: ...
    def check_permissions(self, permissions: list[str] | tuple[str, ...]) -> PermissionCheckResponse: ...
    def ingest(
        self, source: str, trajectories: list[ClaudeCodeTrajectory | CodexTrajectory | CopilotTrajectory | ApertureLog]
    ) -> IngestResponse: ...
    def put_agent_relationship(
        self, *, child_session_id: str, relationship: AgentRelationshipRequest
    ) -> AgentRelationshipResponse: ...
    def ingest_append(
        self,
        *,
        session_id: str,
        anchor_trajectory_hash: str,
        source: str,
        trajectory: ClaudeCodeTrajectory | CodexTrajectory | CopilotTrajectory,
    ) -> IngestResponse: ...
    def grade(
        self,
        *,
        session_id: str | None = None,
        trajectory_ids: list[str] | None = None,
        messages: list[list[ChatMessage]] | None = None,
        grader_ids: list[str],
        tool_call_run_kind: str | None = None,
        tool_use_id: str | None = None,
    ) -> GradeResponse: ...
    def list_monitors(self) -> MonitorsResponse: ...
    def grade_by_role(
        self,
        role: str,
        *,
        session_id: str | None = None,
        trajectory_ids: list[str] | None = None,
        messages: list[list[ChatMessage]] | None = None,
        input: Mapping[str, Any] | None = None,
        tool_use_id: str | None = None,
    ) -> GradeResponse: ...
    @overload
    def pre_tool_use_hook(
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
    def pre_tool_use_hook(
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
    def pre_tool_use_hook(
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
    def pre_tool_use_hook(
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
    def aperture_entire_request_hook(self, payload: Mapping[str, Any]) -> ApertureHookAccepted: ...
    @overload
    def pre_tool_use(
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
    def pre_tool_use(
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
    def list_graders(
        self,
        limit: int = 100,
        offset: int = 0,
    ) -> GraderListResponse: ...
    def create_grader(
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
    ) -> GraderDetail: ...
    def get_grader(self, grader_id: str, version: int | None = None) -> GraderDetail: ...
    def update_grader(self, grader_id: str, **updates: object) -> GraderDetail: ...
    def delete_grader(self, grader_id: str) -> None: ...
    def search_graders(
        self,
        query: str,
        limit: int = 100,
        offset: int = 0,
    ) -> GraderSearchResponse: ...
    def list_grader_models(self) -> ModelsConfig: ...
    def list_sessions(
        self,
        limit: int = 100,
        offset: int = 0,
        sort_by: str = "ended_at",
        sort_order: str = "desc",
    ) -> SessionListResponse: ...
    def list_session_subagents(self, session_id: str, *, limit: int = 20, offset: int = 0) -> SubagentListResponse: ...
    def search_sessions(
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
    ) -> SessionListResponse: ...
    def search_tool_calls(
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
    ) -> ToolCallListResponse: ...
    def get_session_aggregates(
        self,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        bucket: str = "day",
        user_id: str | UUID | None = None,
        *,
        severity_threshold: str,
    ) -> SessionAggregatesResponse: ...
    def get_org_managed_settings(self, path: str = "settings.yaml") -> OrgManagedSettingsDoc: ...
    def update_org_managed_settings(
        self, yaml: str, *, expected_version: int, path: str = "settings.yaml"
    ) -> OrgManagedSettingsDoc: ...
    def get_org_managed_settings_schema(self, path: str = "settings.yaml") -> dict[str, Any]: ...
    def resolve_org_managed_settings(self, path: str = "settings.yaml") -> OrgManagedSettingsResolved: ...
    def get_org_managed_settings_monitors(self, path: str = "settings.yaml") -> ActivatedMonitorsResponse: ...
    def get_monitor_customization(self) -> MonitorCustomizationResponse: ...
    def update_monitor_customization(self, instructions: str) -> MonitorCustomizationResponse: ...
    def get_grading_usage(
        self,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        bucket: str = "day",
        kind: str = "all",
        user_id: str | UUID | None = None,
        model: str | None = None,
        grader_id: str | UUID | None = None,
    ) -> GradingUsageResponse: ...
    def get_usage_limits(self) -> UsageLimitsResponse: ...
    def get_session_filter_options(self) -> SessionFilterOptionsResponse: ...
    def get_session(self, session_id: str) -> SessionDetailResponse: ...
    def get_session_tool_call_decision(self, session_id: str, tool_use_id: str) -> ToolCallFindingsResponse: ...
    def get_session_tool_call(self, session_id: str, tool_use_id: str) -> ToolCallDetailResponse: ...
    def scrub_session_content(self, session_id: str) -> None: ...
    def request_deep_review(self, session_id: str) -> DeepReviewRequestResponse: ...
    def get_deep_review_request(self, session_id: str, operation_id: str) -> DeepReviewRequestResponse: ...
    def get_current_deep_review(self, session_id: str) -> SessionDeepReviewResponse: ...
    def list_trajectories(self, session_id: str) -> TrajectoryListInSessionResponse: ...
    def get_trajectory(
        self, session_id: str, trajectory_id: str, view: TrajectoryView = TrajectoryView.TRUNCATED
    ) -> TrajectoryDetailResponse: ...
    def get_message(self, session_id: str, message_ref: str) -> MessageDetailResponse: ...
    def list_users(self, limit: int = 100, offset: int = 0) -> UserListResponse: ...
    def list_my_session_content_access_requests(
        self,
        *,
        session_id: UUID | None = None,
        status: SessionContentAccessRequestStatus | None = None,
        active_only: bool = False,
        limit: int = 20,
        offset: int = 0,
    ) -> SessionContentAccessRequestListResponse: ...
    def request_session_content_access(self, session_id: UUID) -> SessionContentAccessRequestSummary: ...
    def list_session_content_access_requests(
        self,
        *,
        status: list[SessionContentAccessRequestStatus] | None = None,
        view: SessionContentAccessRequestView | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> AdminSessionContentAccessRequestListResponse: ...
    def get_user(self, user_id: str) -> UserSummary: ...
    def review_session_content_access_request(
        self, request_id: UUID, body: ReviewSessionContentAccessRequest
    ) -> SessionContentAccessRequestSummary: ...
    def revoke_session_content_access_request(self, request_id: UUID) -> SessionContentAccessRequestSummary: ...
    def get_me(self) -> UserSummary: ...
    def health(self) -> HealthResponse: ...
    def version(self) -> VersionResponse: ...
    def ingest_and_grade(
        self,
        source: str,
        trajectories: list[ClaudeCodeTrajectory | CodexTrajectory | CopilotTrajectory | ApertureLog],
        grader_ids: list[str],
    ) -> tuple[IngestResponse, GradeResponse]: ...

    # ---- Pagination (explicitly defined in sync_client.py) ----

    def list_sessions_iter(
        self,
        page_size: int = 100,
        sort_by: str = "ended_at",
        sort_order: str = "desc",
    ) -> Iterator[SessionSummary]: ...
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
    ) -> Iterator[SessionSummary]: ...
