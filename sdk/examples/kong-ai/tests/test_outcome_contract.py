"""Verify matched native tools are released only for consistent Watcher outcomes."""

import httpx
import pytest
from watcher_kong_ai.bridge import evaluate

from watcher_sdk import AsyncWatcherClient


@pytest.mark.parametrize(
    "changes,allowed",
    [
        pytest.param(
            {"decision": "deferred", "judged_decision": None, "decision_source": "bypass"},
            False,
            id="enforce-cannot-use-an-unnamed-ingestion-acknowledgement",
        ),
        pytest.param({"judged_decision": None}, False, id="enforce-allow-needs-a-judgment"),
        pytest.param({"judged_decision": "deny"}, False, id="enforce-allow-cannot-override-deny"),
        pytest.param({"enforcement_mode": "observe"}, False, id="observe-must-defer"),
        pytest.param(
            {"enforcement_mode": "paused", "decision": "deferred", "judged_decision": None},
            False,
            id="paused-needs-bypass-provenance",
        ),
        pytest.param({"decision_source": "bypass"}, False, id="enforce-cannot-bypass-a-named-call"),
        pytest.param({"decision_source": "grading_error"}, False, id="grading-failure-needs-error-details"),
        pytest.param(
            {"grading_error": {"code": "timeout", "message": "Fixture timeout"}},
            False,
            id="rule-result-cannot-carry-a-grading-error",
        ),
        pytest.param(
            {"decision_source": "grading_error", "grading_error": {"code": "timeout", "message": "Fixture timeout"}},
            True,
            id="administrator-grading-failure-allow-is-preserved",
        ),
        pytest.param(
            {
                "enforcement_mode": "observe",
                "decision": "deferred",
                "judged_decision": "escalate",
                "decision_source": "grading_error",
                "grading_error": {"code": "timeout", "message": "Fixture timeout"},
            },
            True,
            id="observe-retains-a-valid-grading-failure-judgment",
        ),
        pytest.param(
            {
                "enforcement_mode": "paused",
                "decision": "deferred",
                "judged_decision": None,
                "decision_source": "bypass",
            },
            True,
            id="paused-deferral-is-preserved",
        ),
    ],
)
async def test_matched_named_tool_outcome_contract(changes, allowed):
    """Exercise SDK decoding and the gateway's actual release boundary together."""
    request = {"model": "fixture", "messages": [{"role": "user", "content": "Read the fixture"}]}
    response = {
        "choices": [
            {
                "index": 0,
                "finish_reason": "tool_calls",
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "native-contract-call",
                            "type": "function",
                            "function": {"name": "read_file", "arguments": '{"path":"fixture.txt"}'},
                        }
                    ],
                },
            }
        ]
    }
    outcome = {
        "tool_use_id": "native-contract-call",
        "decision": "allow",
        "judged_decision": "allow",
        "decision_source": "rule",
        "enforcement_mode": "enforce",
        "verdict": {},
        "latency_ms": 1,
        **changes,
    }
    async with AsyncWatcherClient(
        "http://watcher.invalid",
        httpx_client=httpx.AsyncClient(
            base_url="http://watcher.invalid",
            transport=httpx.MockTransport(lambda _: httpx.Response(200, json=[outcome])),
        ),
    ) as client:
        assert await evaluate(client, request, response, conversation_id="kong:contract-fixture") is allowed
