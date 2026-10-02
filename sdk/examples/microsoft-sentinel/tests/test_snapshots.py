"""Verify session selection and content opt-in against real public-SDK serialization."""

import copy
import json
from datetime import UTC, datetime
from uuid import UUID

import httpx
import pytest
from watcher_microsoft_sentinel.snapshots import SessionSnapshot, fetch_session_snapshots

from watcher_sdk import AsyncWatcherClient

SESSION_ID = "68c777a8-48d8-4ebf-8992-6d9b5c770b60"
START = datetime(2026, 9, 1, tzinfo=UTC)
END = datetime(2026, 9, 2, tzinfo=UTC)


def source_rows():
    summary = {
        "session_id": SESSION_ID,
        "agent_platform": "other",
        "trajectory_count": 1,
        "message_count": 2,
        "started_at": "2026-08-31T23:00:00Z",
        "ended_at": "2026-09-03T01:00:00Z",
        "max_score": 9,
        "max_gateway_score": 8,
        "deep_review_severity": 9,
        "user_email": "hidden@example.invalid",
        "metadata": {"private": "not in summaries"},
        "permission_decisions": {"auto_denied": 1, "would_escalated": 2, "user_email": "hidden@example.invalid"},
    }
    trajectory = {
        "session_id": SESSION_ID,
        "trajectory_id": "source-hash",
        "message_count": 2,
        "first_timestamp": "2026-09-01T01:00:00Z",
        "last_timestamp": "2026-09-01T02:00:00Z",
        "source": "other",
    }
    detail = {
        "session_id": SESSION_ID,
        "trajectory_id": "source-hash",
        "source": "other",
        "created_at": "2026-09-01T01:00:00Z",
        "metadata": {"native_field": "preserved"},
        "grades": [],
        "messages": [
            {"role": "user", "content": "Explicit private transcript"},
            {"role": "assistant", "content": "Result", "custom_field": {"integer": 1, "boolean": False}},
        ],
        "tool_call_decisions": {},
    }
    return {"summary": summary, "trajectory": trajectory, "detail": detail}


def transport(rows, seen, *, modifier=None):
    def handle(request):
        seen.append(request)
        if request.url.path == "/v1/sessions/search":
            body = json.loads(request.content)
            assert body["filters"].get("severities") is None
            assert body["sort_by"] == "started_at" and body["sort_order"] == "asc"
            page = {"sessions": [rows["summary"]], "total": 1, "limit": 200, "offset": 0}
            return httpx.Response(200, json=modifier(page) if modifier else page)
        if request.url.path.endswith("/trajectories"):
            return httpx.Response(200, json={"trajectories": [rows["trajectory"]], "total": 1})
        assert request.url.params["view"] == "extended"
        return httpx.Response(200, json=rows["detail"])

    return handle


async def fetch(rows=None, *, content=False, modifier=None, **kwargs):
    seen = []
    async with AsyncWatcherClient(
        "http://fixture",
        httpx_client=httpx.AsyncClient(
            base_url="http://fixture",
            transport=httpx.MockTransport(transport(rows or source_rows(), seen, modifier=modifier)),
        ),
    ) as client:
        records = await fetch_session_snapshots(client, start=START, end=END, include_transcripts=content, **kwargs)
    return {"records": records, "requests": seen}


async def test_default_summary_does_not_fetch_or_export_private_content():
    result = await fetch()
    assert len(result["requests"]) == 1
    assert len(result["records"]) == 1
    record = result["records"][0]
    assert record.record_type == "session_summary" and record.payload["max_gateway_score"] == 8
    assert "hidden@example.invalid" not in record.model_dump_json()
    assert "not in summaries" not in record.model_dump_json()
    assert record.payload["permission_decisions"] == {"auto_denied": 1, "would_escalated": 2}
    # Activity-overlap selection includes a session that starts before and ends after the window.
    assert record.occurred_at > END


async def test_explicit_content_uses_extended_view_and_preserves_native_fields():
    result = await fetch(content=True)
    assert len(result["requests"]) == 3
    transcript = result["records"][1]
    assert transcript.record_type == "transcript" and transcript.trajectory_id == "source-hash"
    assert transcript.payload["messages"][0]["content"] == "Explicit private transcript"
    assert transcript.payload["metadata"]["native_field"] == "preserved"
    assert transcript.payload["messages"][1]["custom_field"] == {"integer": 1, "boolean": False}


@pytest.mark.parametrize(
    "change",
    [
        {"total": 0},
        {"offset": 1},
        {"limit": 1},
        {"total": -1},
        {"sessions": []},
    ],
)
async def test_inconsistent_pages_do_not_produce_export_records(change):
    with pytest.raises(ValueError):
        await fetch(modifier=lambda page: {**page, **change})


@pytest.mark.parametrize("which", ["summary-session", "trajectory-session", "detail-session", "detail-trajectory"])
async def test_wrong_source_identity_is_rejected(which):
    rows = source_rows()
    if which == "summary-session":
        rows["summary"]["session_id"] = "not-a-uuid"
    elif which == "trajectory-session":
        rows["trajectory"]["session_id"] = "bd7f995f-e68a-4a13-8a09-e195af0e2e98"
    elif which == "detail-session":
        rows["detail"]["session_id"] = "bd7f995f-e68a-4a13-8a09-e195af0e2e98"
    else:
        rows["detail"]["trajectory_id"] = "other-hash"
    with pytest.raises(ValueError):
        await fetch(rows, content=True)


async def test_total_content_budget_is_checked_before_returning_records():
    with pytest.raises(ValueError, match="byte budget"):
        await fetch(content=True, max_total_bytes=1)


async def test_source_outside_activity_window_is_rejected():
    rows = source_rows()
    rows["summary"]["ended_at"] = "2026-08-31T23:30:00Z"
    with pytest.raises(ValueError, match="activity window"):
        await fetch(rows)


def test_fingerprint_changes_with_exported_source_fields():
    record = SessionSnapshot(
        session_id=UUID(SESSION_ID), occurred_at=START, record_type="session_summary", payload={"max_score": 7}
    )
    same = copy.deepcopy(record)
    changed = record.model_copy(update={"payload": {"max_score": 9}})
    assert record.fingerprint() == same.fingerprint()
    assert record.fingerprint() != changed.fingerprint()


async def test_live_denial_without_deep_review_is_included():
    rows = source_rows()
    rows["summary"].update(max_score=None, deep_review_severity=None, max_gateway_score=9)
    result = await fetch(rows)
    assert len(result["records"]) == 1
    assert result["records"][0].payload["max_gateway_score"] == 9


async def test_deep_review_can_select_a_session_without_live_score():
    rows = source_rows()
    rows["summary"].update(max_gateway_score=None, deep_review_severity=8)
    assert len((await fetch(rows))["records"]) == 1


async def test_default_filter_does_not_export_low_or_unscored_content_without_denial():
    for score in (None, 3, 6):
        rows = source_rows()
        rows["summary"].update(max_gateway_score=score, deep_review_severity=None, permission_decisions={})
        result = await fetch(rows, content=True)
        assert result["records"] == []
        assert len(result["requests"]) == 1


async def test_all_severities_explicitly_includes_unscored():
    rows = source_rows()
    rows["summary"].update(max_gateway_score=None, deep_review_severity=None)
    assert len((await fetch(rows, severities=[]))["records"]) == 1


@pytest.mark.parametrize("category", ["human_denied", "auto_denied", "would_denied", "would_escalated"])
@pytest.mark.parametrize("score", [None, 3])
async def test_default_selection_preserves_denied_sessions_without_inventing_severity(category, score):
    rows = source_rows()
    rows["summary"].update(
        max_score=None, max_gateway_score=score, deep_review_severity=None, permission_decisions={category: 1}
    )
    result = await fetch(rows)
    assert len(result["requests"]) == len(result["records"]) == 1
    payload = result["records"][0].payload
    assert payload["max_gateway_score"] == score
    assert payload["deep_review_severity"] is None
    assert payload["permission_decisions"] == {category: 1}


@pytest.mark.parametrize("counts", [None, {}, {"auto_denied": 0}, {"human_allowed": 1}])
async def test_unscored_sessions_without_denial_are_not_selected_by_default(counts):
    rows = source_rows()
    rows["summary"].update(max_gateway_score=None, deep_review_severity=None, permission_decisions=counts)
    assert (await fetch(rows))["records"] == []


async def test_explicit_score_filter_does_not_assign_a_band_to_unscored_denial():
    rows = source_rows()
    rows["summary"].update(max_gateway_score=None, deep_review_severity=None, permission_decisions={"auto_denied": 1})
    assert (await fetch(rows, severities=["high", "critical"]))["records"] == []
