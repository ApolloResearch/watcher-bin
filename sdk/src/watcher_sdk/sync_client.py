"""Synchronous Watcher SDK client — wraps AsyncWatcherClient for sync code.

Uses anyio.from_thread to call async methods from synchronous code.
This works correctly in Jupyter notebooks and other environments with
existing event loops, unlike asyncio.run().

API methods are auto-delegated to the async client via ``__getattr__``.
See ``sync_client.pyi`` for type stubs providing IDE autocomplete and
type checker support.
"""

from __future__ import annotations

import functools
from collections.abc import Iterator
from contextlib import AbstractContextManager
from datetime import datetime
from typing import Self

import anyio.from_thread
import httpx

from watcher_sdk._generated.models.ingest_response import IngestResponse
from watcher_sdk._generated.models.session_summary import SessionSummary
from watcher_sdk._generated.models.user_filter import UserFilter
from watcher_sdk.client import AsyncWatcherClient


class WatcherClient:
    """Synchronous client for the Watcher API.

    Mirrors every method on AsyncWatcherClient with identical signatures and
    return types. Most methods are auto-delegated via ``__getattr__``; only
    methods with different sync behavior (iterators, lifecycle) are defined
    explicitly.

    Usage::

        with WatcherClient("http://localhost:8000") as client:
            sessions = client.list_sessions()
            for session in client.list_sessions_iter():
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
        """Initialize the sync Watcher client.

        Args:
            base_url: Base URL of the Watcher API server.
            api_key: Optional API key for authentication (sent as x-api-key header).
            access_token: Optional JWT access token (sent as Authorization: Bearer header).
                If both api_key and access_token are provided, access_token takes precedence.
            timeout: Request timeout in seconds.
            max_retries: Maximum number of retries for transient failures.
            httpx_client: Optional pre-configured httpx.AsyncClient (for testing).
            manage_external_httpx_client_lifecycle: Passed through to :class:`AsyncWatcherClient`.
        """
        self._async_client = AsyncWatcherClient(
            base_url=base_url,
            api_key=api_key,
            access_token=access_token,
            timeout=timeout,
            max_retries=max_retries,
            httpx_client=httpx_client,
            manage_external_httpx_client_lifecycle=manage_external_httpx_client_lifecycle,
        )
        self._portal: anyio.from_thread.BlockingPortal | None = None
        self._portal_cm: AbstractContextManager[anyio.from_thread.BlockingPortal] | None = None

    def _run(self, coro):  # pyright: ignore[reportUnknownParameterType]
        """Run an async coroutine synchronously via the blocking portal."""
        if self._portal is None:
            raise RuntimeError("Client is not open. Use 'with WatcherClient() as client:' or call client.open()")
        return self._portal.call(lambda: coro)

    def _ingest_incremental(self, body: bytes) -> IngestResponse:
        """Send an internal exact-byte upload using the sync client's portal."""
        return self._run(self._async_client._ingest_incremental(body))

    def __getattr__(self, name: str):  # pyright: ignore[reportUnknownParameterType]
        """Auto-delegate API method calls to the async client.

        Any attribute not explicitly defined on WatcherClient is looked up on
        AsyncWatcherClient. If it's callable (an API method), a sync wrapper
        is returned that runs the async method via the blocking portal.
        The wrapper is cached on the instance for subsequent calls.
        """
        if name.startswith("_"):
            raise AttributeError(name)

        async_attr = getattr(self._async_client, name)
        if not callable(async_attr):
            return async_attr

        @functools.wraps(async_attr)
        def wrapper(*args, **kwargs):  # pyright: ignore[reportUnknownParameterType]
            return self._run(async_attr(*args, **kwargs))

        # Cache the wrapper on the instance to avoid recreating it each call
        setattr(self, name, wrapper)
        return wrapper

    def open(self) -> None:
        """Open the client and start the async event loop portal."""
        cm = anyio.from_thread.start_blocking_portal(backend="asyncio")
        self._portal = cm.__enter__()
        self._portal_cm = cm
        self._portal.call(self._async_client.__aenter__)

    def close(self) -> None:
        """Close the client and shut down the async event loop portal."""
        if self._portal is not None:
            try:
                self._portal.call(lambda: self._async_client.__aexit__(None, None, None))
            finally:
                if self._portal_cm is not None:
                    self._portal_cm.__exit__(None, None, None)
                    self._portal_cm = None
                self._portal = None

    # ---- Pagination iterators (sync-specific, not delegated) ----

    def list_sessions_iter(
        self,
        page_size: int = 100,
        sort_by: str = "ended_at",
        sort_order: str = "desc",
    ) -> Iterator[SessionSummary]:
        """Iterate over all sessions, auto-paginating.

        Fetches pages on demand. Each page makes an HTTP request.

        Args:
            page_size: Number of sessions per page.
            sort_by: Field to sort by ('ended_at' or 'started_at').
            sort_order: Sort direction ('asc' or 'desc').
        """
        offset = 0
        while True:
            response = self.list_sessions(limit=page_size, offset=offset, sort_by=sort_by, sort_order=sort_order)
            yield from response.sessions
            offset += page_size
            if offset >= response.total:
                break

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
    ) -> Iterator[SessionSummary]:
        """Iterate over search results, auto-paginating.

        Sessions with no messages never match, regardless of filters.

        Args:
            start_date: Include only sessions with activity at or after this datetime.
                A session's recorded span runs from its first through its latest
                message, so a session still in progress matches if it has had
                activity at or after this time.
            end_date: Include only sessions that started on or before this datetime.
            external_ids: Filter by external ID mappings.
            agent_platforms: Filter by agent platforms.
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
            users: Owner selection, forwarded on every page. See
                AsyncWatcherClient.search_sessions for include/exclude semantics,
                validation, and required permissions.
            sources: Ingestion sources to match, forwarded on every page. See
                AsyncWatcherClient.search_sessions for retained-message semantics.
        """
        offset = 0
        while True:
            response = self.search_sessions(
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
            )
            yield from response.sessions
            offset += page_size
            if offset >= response.total:
                break

    # ---- Context manager ----

    def __enter__(self) -> Self:
        """Enter sync context manager."""
        self.open()
        return self

    def __exit__(self, *args: object) -> None:
        """Exit sync context manager."""
        self.close()
