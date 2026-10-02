"""Exercise the installed public SDK, source-window invariants and privacy allowlist."""

import json
from datetime import UTC, datetime
from uuid import UUID

import httpx
import pytest
from pydantic import ValidationError
from watcher_microsoft_sentinel import DecisionRecord, ExportError, fetch_records

from watcher_sdk import AsyncWatcherClient

START = datetime(2026, 7, 1, tzinfo=UTC)
END = datetime(2026, 7, 2, tzinfo=UTC)


def row(index=1, **updates):
    return {
        "tool_call_id": str(UUID(int=index)),
        "session_id": str(UUID(int=100)),
        "occurred_at": "2026-07-01T10:00:00.123456+00:00",
        "tool_use_id": f"source-call-{index}",
        "message_ref": "private-message-reference",
        "tool_name": "customer_tool",
        "severity_score": 7,
        "coverage_state": "decided",
        "decision_category": "auto_denied",
        "content_state": "available",
        "user_email": "person@example.invalid",
        "user_first_name": "Private Person",
        "tool_input_preview": "PRIVATE_ARGUMENTS",
        "decision_summary": "PRIVATE_SUMMARY",
        **updates,
    }


def page(rows=None, total=None, offset=0, limit=200):
    rows = [row()] if rows is None else rows
    return {"tool_calls": rows, "total": len(rows) if total is None else total, "offset": offset, "limit": limit}


async def get_pages(pages, *, max_pages=100):
    seen = []

    def handler(request):
        seen.append(json.loads(request.content))
        return httpx.Response(200, json=pages[min(len(seen) - 1, len(pages) - 1)])

    async with AsyncWatcherClient(
        "https://watcher.test",
        max_retries=0,
        httpx_client=httpx.AsyncClient(base_url="https://watcher.test", transport=httpx.MockTransport(handler)),
    ) as watcher:
        return await fetch_records(watcher, start=START, end=END, page_size=1, max_pages=max_pages)


@pytest.mark.parametrize(
    "mutation",
    ["total", "duplicate", "offset", "limit", "outside", "order", "empty", "maximum", "too-many", "over-total"],
)
async def test_unstable_or_inconsistent_source_is_rejected(mutation):
    pages = [page([row(1)], total=2, limit=1), page([row(2)], total=2, offset=1, limit=1)]
    maximum = 100
    if mutation == "total":
        pages[1]["total"] = 3
    elif mutation == "duplicate":
        pages[1]["tool_calls"] = [row(1)]
    elif mutation == "offset":
        pages[1]["offset"] = 0
    elif mutation == "limit":
        pages[1]["limit"] = 2
    elif mutation == "outside":
        pages[1]["tool_calls"] = [row(2, occurred_at="2025-01-01T00:00:00Z")]
    elif mutation == "order":
        pages[1]["tool_calls"] = [row(2, occurred_at="2026-07-01T09:00:00Z")]
    elif mutation == "empty":
        pages[1]["tool_calls"] = []
    elif mutation == "maximum":
        maximum = 1
    elif mutation == "over-total":
        pages[0]["total"] = 0
    else:
        pages[1]["tool_calls"] = [row(2), row(3)]
    with pytest.raises(ExportError):
        await get_pages(pages, max_pages=maximum)


async def test_empty_window():
    assert await get_pages([page([], total=0, limit=1)]) == []


@pytest.mark.parametrize(
    "start,end",
    [
        (START, START),
        (END, START),
        (START.replace(tzinfo=None), END),
        (START, END.replace(tzinfo=None)),
        (datetime(1969, 1, 1, tzinfo=UTC), END),
    ],
)
async def test_invalid_window_fails_before_reading(start, end):
    async with AsyncWatcherClient(
        "https://watcher.test",
        httpx_client=httpx.AsyncClient(transport=httpx.MockTransport(lambda request: pytest.fail("source queried"))),
    ) as watcher:
        with pytest.raises(ValueError):
            await fetch_records(watcher, start=start, end=end)


@pytest.mark.parametrize("page_size,max_pages", [(0, 1), (1001, 1), (1, 0)])
async def test_invalid_page_bounds(page_size, max_pages):
    async with AsyncWatcherClient(
        "https://watcher.test",
        httpx_client=httpx.AsyncClient(transport=httpx.MockTransport(lambda request: pytest.fail("source queried"))),
    ) as watcher:
        with pytest.raises(ValueError):
            await fetch_records(watcher, start=START, end=END, page_size=page_size, max_pages=max_pages)


@pytest.mark.parametrize(
    "updates",
    [
        {"severity_score": True},
        {"severity_score": "7"},
        {"severity_score": 7.0},
        {"coverage_state": "PRIVATE_TEXT"},
        {"decision_category": "PRIVATE_TEXT"},
        {"content_state": "PRIVATE_TEXT"},
        {"occurred_at": "2026-07-01T00:00:00"},
        {"occurred_at": "1969-07-01T00:00:00Z"},
        {"tool_call_id": "not-a-uuid"},
    ],
)
def test_content_fields_and_malformed_classifications_are_rejected(updates):
    with pytest.raises(ValidationError):
        DecisionRecord.model_validate(row(**updates))


def test_fingerprint_tracks_exported_version_and_normalizes_time():
    original = DecisionRecord.model_validate(row())
    same = DecisionRecord.model_validate(
        row(user_email="other@example.invalid", occurred_at="2026-07-01T12:00:00.123456+02:00")
    )
    changed = DecisionRecord.model_validate(row(severity_score=8))
    assert original.fingerprint() == same.fingerprint()
    assert original.fingerprint() != changed.fingerprint()
    assert "PRIVATE" not in original.model_dump_json()


async def test_inclusive_boundaries_and_stable_ties():
    records = await get_pages(
        [
            page([row(1, occurred_at=START.isoformat())], total=3, limit=1),
            page([row(2, occurred_at=START.isoformat())], total=3, offset=1, limit=1),
            page([row(3, occurred_at=END.isoformat())], total=3, offset=2, limit=1),
        ]
    )
    assert [record.tool_call_id.int for record in records] == [1, 2, 3]


@pytest.mark.parametrize(
    "field,value", [("total", True), ("total", "1"), ("total", -1), ("offset", False), ("limit", True)]
)
async def test_malformed_numeric_pagination_is_refused(field, value):
    response = page([row()], total=1, limit=1)
    response[field] = value
    with pytest.raises(ExportError):
        await get_pages([response])


@pytest.mark.parametrize("score", [-1, 0, 1, 10, 11, 101])
def test_sdk_integer_score_is_preserved_without_an_inferred_range(score):
    record = DecisionRecord.model_validate(row(severity_score=score))
    assert record.severity_score == score
