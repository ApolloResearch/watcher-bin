"""Watcher SDK — Python client for the Watcher API (Watcher monitoring platform).

Provides both synchronous (WatcherClient) and asynchronous (AsyncWatcherClient)
clients for ingesting trajectories, grading them, and querying sessions. All API
errors are mapped to a typed exception hierarchy rooted at WatcherError, so callers
can handle specific failure modes (rate limits, auth, validation) independently.

Synchronous usage::

    from watcher_sdk import WatcherClient

    with WatcherClient("http://localhost:8000") as client:
        # Ingest and grade in one call
        ingest_resp, grade_resp = client.ingest_and_grade(
            source="my-pipeline",
            trajectories=[trajectory],
        )

        # List sessions with pagination
        sessions = client.list_sessions(limit=50, offset=0)

        # Iterate over all sessions (auto-paginates)
        for session in client.list_sessions_iter():
            print(session.session_id)

        # Get full session detail
        detail = client.get_session(session_id="abc-123")

Async usage::

    from watcher_sdk import AsyncWatcherClient

    async with AsyncWatcherClient("http://localhost:8000") as client:
        sessions = await client.list_sessions()
        async for session in client.list_sessions_iter():
            print(session.session_id)

Error handling::

    from watcher_sdk import WatcherClient, WatcherNotFoundError, WatcherRateLimitError

    with WatcherClient("http://localhost:8000") as client:
        try:
            detail = client.get_session("nonexistent-id")
        except WatcherNotFoundError:
            print("Session not found")
        except WatcherRateLimitError as e:
            print(f"Rate limited, retry after {e.retry_after}s")

Exported models (from the generated API schema):
    ApertureLog, AvailableSessionDetailResponse, ClaudeCodeTrajectory, CodexTrajectory, CopilotTrajectory,
    CreateGraderRequest, GradeRequest, GradeResponse,
    GradeResult, GraderDetail, GraderListResponse, GraderSearchRequest,
    GraderSearchResponse, GraderSummary, HealthResponse, IngestRequest,
    ModelsConfig, OrgManagedSettingsDoc, OrgManagedSettingsResolved, SuggestedModel,
    IngestResponse, MessageDetailResponse, ScoreDefinition, SessionDetailResponse,
    ScrubbedSessionDetailResponse, SessionListResponse, SessionSearchParams, SessionSummary,
    ToolCallDecisionDetail, TrajectoryDetailResponse, TrajectoryListInSessionResponse, TrajectorySummary,
    TrajectoryView, UpdateGraderRequest
"""

from watcher_sdk._generated.models import (
    AgentRelationshipRequest,
    AgentRelationshipResponse,
    ApertureLog,
    AvailableSessionDetailResponse,
    ClaudeCodeAgentIdentity,
    ClaudeCodeTrajectory,
    CodexTrajectory,
    CopilotTrajectory,
    CreateGraderRequest,
    GraderDetail,
    GradeRequest,
    GradeResponse,
    GradeResult,
    GraderListResponse,
    GraderSearchRequest,
    GraderSearchResponse,
    GraderSummary,
    HealthResponse,
    IngestRequest,
    IngestResponse,
    IngestToolCallReference,
    MessageDetailResponse,
    ModelsConfig,
    OrgManagedSettingsDoc,
    OrgManagedSettingsResolved,
    RelatedSessionSummary,
    ResolvedIngestToolCall,
    ScoreDefinition,
    ScrubbedSessionDetailResponse,
    SessionAggregatesResponse,
    SessionFilterOptionsResponse,
    SessionListResponse,
    SessionSearchParams,
    SessionSummary,
    SpawnedSubagent,
    SubagentListResponse,
    SuggestedModel,
    ToolCallDecisionDetail,
    ToolCallDetailResponse,
    ToolCallFindingsResponse,
    ToolCallResult,
    TrajectoryDetailResponse,
    TrajectoryListInSessionResponse,
    TrajectorySummary,
    TrajectoryView,
    UpdateGraderRequest,
    UserFilter,
    UserFilterMode,
    UserProfile,
    UserProfileMembershipsItem,
)
from watcher_sdk.auth_support import REFRESH_TOKEN_COOKIE_NAME, AuthExchangeResult, AuthLogoutResult
from watcher_sdk.client import AsyncWatcherClient, LocalPreToolUseDecision, SessionDetailResponse
from watcher_sdk.errors import (
    WatcherAPIError,
    WatcherAuthenticationError,
    WatcherConnectionError,
    WatcherError,
    WatcherNotFoundError,
    WatcherRateLimitError,
    WatcherTimeoutError,
    WatcherValidationError,
)
from watcher_sdk.integration_auth import IntegrationAuth, SDKLoginAuth, discover_logins, verify_integration_auth
from watcher_sdk.local_auth import WatcherLoginAuth, async_client_from_watcher
from watcher_sdk.login import DeviceLoginPrompt, login, logout
from watcher_sdk.sync_client import WatcherClient

__all__ = [
    # Auth (refresh in httpOnly cookie)
    "AuthExchangeResult",
    "AuthLogoutResult",
    "REFRESH_TOKEN_COOKIE_NAME",
    # Clients
    "AsyncWatcherClient",
    "WatcherLoginAuth",
    "async_client_from_watcher",
    "IntegrationAuth",
    "SDKLoginAuth",
    "discover_logins",
    "verify_integration_auth",
    "DeviceLoginPrompt",
    "login",
    "logout",
    "WatcherClient",
    # Errors
    "WatcherAPIError",
    "WatcherAuthenticationError",
    "WatcherConnectionError",
    "WatcherError",
    "WatcherNotFoundError",
    "WatcherRateLimitError",
    "WatcherTimeoutError",
    "WatcherValidationError",
    # Models
    "AgentRelationshipRequest",
    "AgentRelationshipResponse",
    "ClaudeCodeAgentIdentity",
    "IngestToolCallReference",
    "ResolvedIngestToolCall",
    "ApertureLog",
    "AvailableSessionDetailResponse",
    "ClaudeCodeTrajectory",
    "CodexTrajectory",
    "CopilotTrajectory",
    "CreateGraderRequest",
    "GradeRequest",
    "GradeResponse",
    "GradeResult",
    "GraderDetail",
    "GraderListResponse",
    "GraderSearchRequest",
    "GraderSearchResponse",
    "GraderSummary",
    "HealthResponse",
    "IngestRequest",
    "LocalPreToolUseDecision",
    "ModelsConfig",
    "OrgManagedSettingsDoc",
    "OrgManagedSettingsResolved",
    "SuggestedModel",
    "IngestResponse",
    "ScoreDefinition",
    "SessionAggregatesResponse",
    "SessionDetailResponse",
    "SessionFilterOptionsResponse",
    "SessionListResponse",
    "SubagentListResponse",
    "RelatedSessionSummary",
    "SpawnedSubagent",
    "SessionSearchParams",
    "SessionSummary",
    "ToolCallDecisionDetail",
    "ToolCallFindingsResponse",
    "ToolCallDetailResponse",
    "ToolCallResult",
    "ScrubbedSessionDetailResponse",
    "MessageDetailResponse",
    "TrajectoryDetailResponse",
    "TrajectoryView",
    "TrajectoryListInSessionResponse",
    "TrajectorySummary",
    "UpdateGraderRequest",
    "UserFilter",
    "UserFilterMode",
    "UserProfile",
    "UserProfileMembershipsItem",
]
