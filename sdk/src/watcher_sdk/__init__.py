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

import importlib
import sys
from types import ModuleType
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
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

# Exports load on first use (PEP 562) rather than at package import. Agent hooks start a
# fresh interpreter per tool call and import ``watcher_sdk.settings_schema``, which runs this
# module first; eager imports here would load the HTTP client and every generated model
# (about half the modules a hook loads) for hooks that never call the API.
_EXPORTS: dict[str, str] = {
    "AgentRelationshipRequest": "watcher_sdk._generated.models",
    "AgentRelationshipResponse": "watcher_sdk._generated.models",
    "ApertureLog": "watcher_sdk._generated.models",
    "AvailableSessionDetailResponse": "watcher_sdk._generated.models",
    "ClaudeCodeAgentIdentity": "watcher_sdk._generated.models",
    "ClaudeCodeTrajectory": "watcher_sdk._generated.models",
    "CodexTrajectory": "watcher_sdk._generated.models",
    "CopilotTrajectory": "watcher_sdk._generated.models",
    "CreateGraderRequest": "watcher_sdk._generated.models",
    "GraderDetail": "watcher_sdk._generated.models",
    "GradeRequest": "watcher_sdk._generated.models",
    "GradeResponse": "watcher_sdk._generated.models",
    "GradeResult": "watcher_sdk._generated.models",
    "GraderListResponse": "watcher_sdk._generated.models",
    "GraderSearchRequest": "watcher_sdk._generated.models",
    "GraderSearchResponse": "watcher_sdk._generated.models",
    "GraderSummary": "watcher_sdk._generated.models",
    "HealthResponse": "watcher_sdk._generated.models",
    "IngestRequest": "watcher_sdk._generated.models",
    "IngestResponse": "watcher_sdk._generated.models",
    "IngestToolCallReference": "watcher_sdk._generated.models",
    "MessageDetailResponse": "watcher_sdk._generated.models",
    "ModelsConfig": "watcher_sdk._generated.models",
    "OrgManagedSettingsDoc": "watcher_sdk._generated.models",
    "OrgManagedSettingsResolved": "watcher_sdk._generated.models",
    "RelatedSessionSummary": "watcher_sdk._generated.models",
    "ResolvedIngestToolCall": "watcher_sdk._generated.models",
    "ScoreDefinition": "watcher_sdk._generated.models",
    "ScrubbedSessionDetailResponse": "watcher_sdk._generated.models",
    "SessionAggregatesResponse": "watcher_sdk._generated.models",
    "SessionFilterOptionsResponse": "watcher_sdk._generated.models",
    "SessionListResponse": "watcher_sdk._generated.models",
    "SessionSearchParams": "watcher_sdk._generated.models",
    "SessionSummary": "watcher_sdk._generated.models",
    "SpawnedSubagent": "watcher_sdk._generated.models",
    "SubagentListResponse": "watcher_sdk._generated.models",
    "SuggestedModel": "watcher_sdk._generated.models",
    "ToolCallDecisionDetail": "watcher_sdk._generated.models",
    "ToolCallDetailResponse": "watcher_sdk._generated.models",
    "ToolCallFindingsResponse": "watcher_sdk._generated.models",
    "ToolCallResult": "watcher_sdk._generated.models",
    "TrajectoryDetailResponse": "watcher_sdk._generated.models",
    "TrajectoryListInSessionResponse": "watcher_sdk._generated.models",
    "TrajectorySummary": "watcher_sdk._generated.models",
    "TrajectoryView": "watcher_sdk._generated.models",
    "UpdateGraderRequest": "watcher_sdk._generated.models",
    "UserFilter": "watcher_sdk._generated.models",
    "UserFilterMode": "watcher_sdk._generated.models",
    "UserProfile": "watcher_sdk._generated.models",
    "UserProfileMembershipsItem": "watcher_sdk._generated.models",
    "REFRESH_TOKEN_COOKIE_NAME": "watcher_sdk.auth_support",
    "AuthExchangeResult": "watcher_sdk.auth_support",
    "AuthLogoutResult": "watcher_sdk.auth_support",
    "AsyncWatcherClient": "watcher_sdk.client",
    "LocalPreToolUseDecision": "watcher_sdk.client",
    "SessionDetailResponse": "watcher_sdk.client",
    "WatcherAPIError": "watcher_sdk.errors",
    "WatcherAuthenticationError": "watcher_sdk.errors",
    "WatcherConnectionError": "watcher_sdk.errors",
    "WatcherError": "watcher_sdk.errors",
    "WatcherNotFoundError": "watcher_sdk.errors",
    "WatcherRateLimitError": "watcher_sdk.errors",
    "WatcherTimeoutError": "watcher_sdk.errors",
    "WatcherValidationError": "watcher_sdk.errors",
    "IntegrationAuth": "watcher_sdk.integration_auth",
    "SDKLoginAuth": "watcher_sdk.integration_auth",
    "discover_logins": "watcher_sdk.integration_auth",
    "verify_integration_auth": "watcher_sdk.integration_auth",
    "WatcherLoginAuth": "watcher_sdk.local_auth",
    "async_client_from_watcher": "watcher_sdk.local_auth",
    "DeviceLoginPrompt": "watcher_sdk.login",
    "login": "watcher_sdk.login",
    "logout": "watcher_sdk.login",
    "WatcherClient": "watcher_sdk.sync_client",
}


def __getattr__(name: str) -> Any:
    """Import an exported name's defining module on first access and cache the result."""
    module = _EXPORTS.get(name)
    if module is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(importlib.import_module(module), name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted({*globals(), *_EXPORTS})


class _Package(ModuleType):
    """Keep an export that shares its name with its own submodule (``login``) bound to the export.

    Importing ``watcher_sdk.login`` binds the submodule on this package, which
    would hide the ``login`` function. Eager imports avoided that by binding the
    function after the submodule loaded; with lazy exports the submodule can load
    at any time, so the rebinding happens here instead.
    """

    def __setattr__(self, name: str, value: object) -> None:
        if isinstance(value, ModuleType) and value.__name__ == _EXPORTS.get(name) == f"{__name__}.{name}":
            value = getattr(value, name)
        super().__setattr__(name, value)


sys.modules[__name__].__class__ = _Package

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
