"""HEC-specific body, channel and replication acknowledgment behavior."""

import json
from uuid import UUID

import httpx
import pytest
from watcher_splunk import AcknowledgmentPending, DecisionRecord, ExportError, HecSink, encode_event


@pytest.mark.parametrize(
    "status,code,attempts",
    [
        (200, 6, 1),
        (200, 24, 1),
        (200, 25, 1),
        (200, 17, 1),
        (400, 6, 1),
        (401, 3, 1),
        (403, 4, 1),
        (503, 9, 3),
        (503, 18, 1),
        (429, 26, 3),
        (429, 27, 3),
        (302, 0, 1),
    ],
)
async def test_status_and_body_must_both_succeed(status, code, attempts):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(
            status,
            headers={"Retry-After": "0", "Location": "https://other.test"},
            json={"code": code, "text": "PRIVATE_ERROR"},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler), follow_redirects=True) as http:
        with pytest.raises(ExportError) as caught:
            await HecSink(http, "https://receiver.test", "fixture").send(b'{"event":1}')
    assert len(calls) == attempts and "PRIVATE_ERROR" not in str(caught.value)


@pytest.mark.parametrize("body", [b"not-json", b"[]", b"{}", b'{"code":false}', b'{"code":"0"}', b'{"code":null}'])
async def test_malformed_or_nonzero_success_body_is_never_accepted(body):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, content=body)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        with pytest.raises(ExportError):
            await HecSink(http, "https://receiver.test", "fixture").send(b'{"event":1}')
    assert len(calls) == 1


async def test_real_ack_channel_polls_until_true_without_resending(http_fixture):
    requests = []
    channel = UUID(int=42)

    def handler(method, path, headers, body):
        assert headers["X-Splunk-Request-Channel"] == str(channel)
        assert headers["Authorization"] == "Splunk fixture"
        requests.append(path)
        if path.endswith("/event"):
            return 200, {}, {"code": 0, "ackId": 0}
        assert path == "/services/collector/ack" and json.loads(body) == {"acks": [0]}
        return 200, {}, {"acks": {"0": len(requests) == 3}}

    async with http_fixture(handler) as endpoint, httpx.AsyncClient(trust_env=False) as http:
        await HecSink(http, endpoint, "fixture", acknowledgments=True, channel=channel, ack_interval=0).send(
            b'{"event":1}'
        )
    assert requests == ["/services/collector/event", "/services/collector/ack", "/services/collector/ack"]


async def test_pending_ack_retains_resume_identity():
    calls = []
    channel = UUID(int=42)

    def handler(request):
        calls.append(request)
        if request.url.path.endswith("/event"):
            return httpx.Response(200, json={"code": 0, "ackId": 7})
        return httpx.Response(200, json={"acks": {"7": len(calls) > 3}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        sink = HecSink(
            http, "https://receiver.test", "fixture", acknowledgments=True, channel=channel, ack_polls=2, ack_interval=0
        )
        with pytest.raises(AcknowledgmentPending) as error:
            await sink.send(b'{"event":1}')
        assert error.value.channel == channel and error.value.ack_id == 7
        await sink.wait_for_ack(error.value.ack_id)
    assert len(calls) == 4 and sum(request.url.path.endswith("/event") for request in calls) == 1


@pytest.mark.parametrize("ack_id", [None, "1x", "1.0", "-1", "+1", " 1", "１", -1, True])
async def test_missing_invalid_ack_id_means_ambiguous_delivery(ack_id):
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"code": 0, "ackId": ack_id}))
    ) as http:
        with pytest.raises(ExportError):
            await HecSink(http, "https://receiver.test", "fixture", acknowledgments=True).send(b'{"event":1}')


@pytest.mark.parametrize("body", [{}, {"acks": []}, {"acks": {"8": True}}, {"acks": {"7": 1}}, {"acks": {"7": "true"}}])
async def test_invalid_poll_response_is_not_confirmation(body):
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, json=body))) as http:
        with pytest.raises(ExportError):
            await HecSink(http, "https://receiver.test", "fixture", acknowledgments=True).wait_for_ack(7)


async def test_poll_http_failure_is_not_automatically_retried():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(503, json={"code": 19})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        with pytest.raises(ExportError):
            await HecSink(http, "https://receiver.test", "fixture", acknowledgments=True).wait_for_ack(7)
    assert len(calls) == 1


@pytest.mark.parametrize(
    "options",
    [
        {"attempts": 0},
        {"attempts": 6},
        {"ack_polls": 0},
        {"ack_polls": 301},
        {"ack_interval": float("nan")},
        {"ack_interval": -1},
        {"ack_interval": 31},
        {"index": ""},
        {"index": "bad\nindex"},
    ],
)
def test_invalid_settings(options):
    with pytest.raises(ValueError):
        HecSink(httpx.AsyncClient(), "https://receiver.test", "fixture", **options)


def test_scrubbed_unscored_event_has_no_fabricated_decision():
    record = DecisionRecord(
        tool_call_id=UUID(int=1),
        session_id=UUID(int=2),
        occurred_at="2026-07-01T00:00:00Z",
        coverage_state="not_evaluated",
        content_state="scrubbed",
    )
    envelope = json.loads(encode_event(record, index="watcher"))
    assert envelope["index"] == "watcher" and envelope["time"] == 1782864000
    assert "severity_score" not in envelope["event"] and "decision_category" not in envelope["event"]
    assert envelope["event"]["content_state"] == "scrubbed"


@pytest.mark.parametrize("failure", ["timeout", "status", "malformed"])
async def test_accepted_event_poll_failure_keeps_resume_identity(failure):
    calls = []
    channel = UUID(int=42)

    def handler(request):
        calls.append(request)
        if request.url.path.endswith("/event"):
            return httpx.Response(200, json={"code": 0, "ackId": 7})
        if failure == "timeout":
            raise httpx.ReadTimeout("fixture")
        if failure == "status":
            return httpx.Response(503, json={"code": 19})
        return httpx.Response(200, content=b"malformed")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        sink = HecSink(http, "https://receiver.test", "fixture", acknowledgments=True, channel=channel)
        with pytest.raises(AcknowledgmentPending) as error:
            await sink.send(b'{"event":1}')
        assert error.value.channel == channel and error.value.ack_id == 7
        assert error.value.__cause__ is not None
    assert len(calls) == 2


@pytest.mark.parametrize(
    "acknowledgment",
    [
        {"ackId": 7},
        {"ackId": "7"},
        {"ackID": 7},
        {"ackID": "7"},
        {"ackId": 7, "ackID": "007"},
    ],
)
async def test_documented_acknowledgment_variants_poll_one_numeric_id(http_fixture, acknowledgment):
    requests = []

    def handler(method, path, headers, body):
        assert method == "POST"
        requests.append(path)
        if path.endswith("/event"):
            return 200, {}, {"code": 0, **acknowledgment}
        assert path == "/services/collector/ack" and json.loads(body) == {"acks": [7]}
        return 200, {}, {"acks": {"7": True}}

    async with http_fixture(handler) as endpoint, httpx.AsyncClient(trust_env=False) as http:
        await HecSink(http, endpoint, "fixture", acknowledgments=True).send(b'{"event":1}')
    assert requests == ["/services/collector/event", "/services/collector/ack"]


@pytest.mark.parametrize(
    "acknowledgment",
    [
        {},
        {"ackId": 7, "ackID": 8},
        {"ackId": 7, "ackID": True},
        {"ackId": "invalid", "ackID": 7},
    ],
)
async def test_absent_invalid_or_conflicting_acknowledgment_aliases_do_not_choose_an_id(acknowledgment):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json={"code": 0, **acknowledgment})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        with pytest.raises(ExportError, match="acknowledgment ID"):
            await HecSink(http, "https://receiver.test", "fixture", acknowledgments=True).send(b'{"event":1}')
    assert len(calls) == 1 and calls[0].url.path == "/services/collector/event"


@pytest.mark.parametrize("status", [200, 302, 429, 503])
@pytest.mark.parametrize("body", [b"PRIVATE_ERROR not-json", b'["PRIVATE_ERROR"]'])
async def test_malformed_body_errors_retain_status_without_echoing_content(status, body):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(status, content=body, headers={"Location": "https://other.test", "Retry-After": "0"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler), follow_redirects=True) as http:
        with pytest.raises(ExportError) as error:
            await HecSink(http, "https://receiver.test", "fixture").send(b'{"event":1}')
    assert f"HTTP {status}" in str(error.value)
    assert "PRIVATE_ERROR" not in str(error.value) and len(calls) == 1
