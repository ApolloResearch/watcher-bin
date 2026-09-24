"""Pagination iterators for Watcher SDK list endpoints.

Provides AsyncIterator implementations that auto-paginate through
list_sessions and search_sessions results. Each iterator lazily fetches
pages on demand and yields individual SessionSummary items, stopping
when all items have been yielded (offset >= total).

These classes are internal to the SDK; callers interact with them via
AsyncWatcherClient.list_sessions_iter() and AsyncWatcherClient.search_sessions_iter().
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable

from watcher_sdk._generated.models.session_list_response import SessionListResponse
from watcher_sdk._generated.models.session_summary import SessionSummary


class PaginatedIterator(AsyncIterator[SessionSummary]):
    """Async iterator that auto-paginates through list_sessions results.

    Fetches pages on demand and yields individual SessionSummary items.
    Stops when all items have been yielded (offset >= total).

    Usage::

        async for session in PaginatedIterator(fetch_page=..., page_size=100):
            print(session.session_id)
    """

    def __init__(
        self,
        fetch_page: Callable[[int], Awaitable[SessionListResponse]],
        page_size: int,
    ) -> None:
        """Initialize the paginated iterator.

        Args:
            fetch_page: Async callable that accepts an integer offset and returns
                a SessionListResponse for that page.
            page_size: Number of items per page. Used to advance the offset after
                each fetch.
        """
        self._fetch_page = fetch_page
        self._page_size = page_size
        self._offset = 0
        self._total: int | None = None
        self._buffer: list[SessionSummary] = []
        self._buffer_index = 0

    def __aiter__(self) -> AsyncIterator[SessionSummary]:
        return self

    async def __anext__(self) -> SessionSummary:
        # If we still have items in the buffer, yield them
        if self._buffer_index < len(self._buffer):
            item = self._buffer[self._buffer_index]
            self._buffer_index += 1
            return item

        # Check if we've exhausted all pages
        if self._total is not None and self._offset >= self._total:
            raise StopAsyncIteration

        # Fetch the next page
        response = await self._fetch_page(self._offset)
        self._total = response.total
        self._buffer = list(response.sessions)
        self._buffer_index = 0
        self._offset += self._page_size

        if not self._buffer:
            raise StopAsyncIteration

        item = self._buffer[self._buffer_index]
        self._buffer_index += 1
        return item


class SearchPaginatedIterator(AsyncIterator[SessionSummary]):
    """Async iterator that auto-paginates through search_sessions results.

    Identical in behavior to PaginatedIterator but kept as a separate class
    for clarity since the fetch function (search_sessions) accepts different
    filter parameters that are captured in the closure.

    Usage::

        async for session in SearchPaginatedIterator(fetch_page=..., page_size=100):
            print(session.session_id)
    """

    def __init__(
        self,
        fetch_page: Callable[[int], Awaitable[SessionListResponse]],
        page_size: int,
    ) -> None:
        """Initialize the search paginated iterator.

        Args:
            fetch_page: Async callable that accepts an integer offset and returns
                a SessionListResponse for that page. Typically a closure over
                search_sessions with filter parameters already bound.
            page_size: Number of items per page. Used to advance the offset after
                each fetch.
        """
        self._fetch_page = fetch_page
        self._page_size = page_size
        self._offset = 0
        self._total: int | None = None
        self._buffer: list[SessionSummary] = []
        self._buffer_index = 0

    def __aiter__(self) -> AsyncIterator[SessionSummary]:
        return self

    async def __anext__(self) -> SessionSummary:
        if self._buffer_index < len(self._buffer):
            item = self._buffer[self._buffer_index]
            self._buffer_index += 1
            return item

        if self._total is not None and self._offset >= self._total:
            raise StopAsyncIteration

        response = await self._fetch_page(self._offset)
        self._total = response.total
        self._buffer = list(response.sessions)
        self._buffer_index = 0
        self._offset += self._page_size

        if not self._buffer:
            raise StopAsyncIteration

        item = self._buffer[self._buffer_index]
        self._buffer_index += 1
        return item
