"""Verify Broadcast parsing, content boundaries and transcript-only SDK submission."""

import copy
import json

import httpx
import pytest
from watcher_openrouter.integration import prepare, submit

from watcher_sdk import AsyncWatcherClient


def payload(*, shape="messages", keys=("gen_ai.prompt", "gen_ai.completion")):
    request = [{"role": "user", "content": "Read fixture"}]
    response = [
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "native-call",
                    "type": "function",
                    "function": {
                        "name": "read_file",
                        "arguments": '{"count":0,"ratio":1.0,"enabled":false,"empty":null}',
                    },
                }
            ],
        }
    ]
    if shape == "objects":
        request = {"model": "fixture", "messages": request}
        response = {"choices": [{"index": 0, "message": response[0], "finish_reason": "tool_calls"}]}
    return {
        "resourceSpans": [
            {
                "scopeSpans": [
                    {
                        "spans": [
                            {
                                "traceId": "trace",
                                "spanId": "native-generation",
                                "startTimeUnixNano": "123",
                                "attributes": [
                                    {"key": "gen_ai.request.model", "value": {"stringValue": "fixture"}},
                                    {"key": keys[0], "value": {"stringValue": json.dumps(request)}},
                                    {"key": keys[1], "value": {"stringValue": json.dumps(response)}},
                                    {"key": "session.id", "value": {"stringValue": "untrusted-client-shared"}},
                                ],
                            }
                        ]
                    }
                ]
            }
        ]
    }


@pytest.mark.parametrize("shape", ["messages", "objects"])
@pytest.mark.parametrize("keys", [("gen_ai.prompt", "gen_ai.completion"), ("span.input", "span.output")])
async def test_documented_attribute_families_submit_typed_content(shape, keys):
    seen = []

    def handler(request):
        if request.url.path.endswith("check-permissions"):
            return httpx.Response(200, json={"granted": True, "missing": []})
        body = json.loads(request.content)
        seen.append(body)
        assert body.get("input") is None and body.get("settings_overrides") is None
        call = body["messages"][-1]["tool_calls"][0]
        assert call["id"] == "native-call" and call["function"] == "read_file"
        assert type(call["arguments"]["count"]) is int and type(call["arguments"]["ratio"]) is float
        assert call["arguments"]["enabled"] is False and call["arguments"]["empty"] is None
        assert body["external_ids"]["other"] != "untrusted-client-shared"
        return httpx.Response(200, json=[])

    async with AsyncWatcherClient(
        "http://fixture",
        httpx_client=httpx.AsyncClient(base_url="http://fixture", transport=httpx.MockTransport(handler)),
    ) as client:
        receipt = await submit(client, payload(shape=shape, keys=keys), namespace="account-one")
    assert receipt.submitted == 1 and receipt.ignored_spans == 0 and len(seen) == 1


def test_retry_identity_and_independent_generations():
    first = payload()
    second = copy.deepcopy(first)
    second["resourceSpans"][0]["scopeSpans"][0]["spans"][0]["spanId"] = "other-generation"
    result = prepare(first, namespace="one").snapshots[0].conversation_id
    assert result == prepare(first, namespace="one").snapshots[0].conversation_id
    assert result != prepare(first, namespace="two").snapshots[0].conversation_id
    assert result != prepare(second, namespace="one").snapshots[0].conversation_id


def test_root_spans_are_counted_without_claiming_a_transcript():
    data = payload()
    data["resourceSpans"][0]["scopeSpans"][0]["spans"].append({"spanId": "root", "attributes": []})
    batch = prepare(data, namespace="one")
    assert len(batch.snapshots) == 1 and batch.ignored_spans == 1


@pytest.mark.parametrize(
    "failure", ["privacy", "missing-output", "duplicate-attribute", "bad-json", "missing-span-id", "multimodal"]
)
async def test_unsupported_batch_fails_before_any_sdk_call(failure):
    data = payload()
    span = data["resourceSpans"][0]["scopeSpans"][0]["spans"][0]
    attributes = span["attributes"]
    if failure == "privacy":
        span["attributes"] = attributes[:1]
    elif failure == "missing-output":
        del attributes[2]
    elif failure == "duplicate-attribute":
        attributes.append(attributes[1])
    elif failure == "bad-json":
        attributes[1]["value"]["stringValue"] = "not JSON"
    elif failure == "missing-span-id":
        del span["spanId"]
    else:
        attributes[1]["value"]["stringValue"] = json.dumps([{"role": "user", "content": [{"type": "image_url"}]}])
    async with AsyncWatcherClient(
        "http://fixture",
        httpx_client=httpx.AsyncClient(
            base_url="http://fixture", transport=httpx.MockTransport(lambda _: pytest.fail("Invalid batch reached SDK"))
        ),
    ) as client:
        with pytest.raises((ValueError, KeyError)):
            await submit(client, data, namespace="one")


def test_empty_otlp_payload_has_zero_generations():
    batch = prepare({"resourceSpans": []}, namespace="one")
    assert batch.snapshots == [] and batch.ignored_spans == 0
