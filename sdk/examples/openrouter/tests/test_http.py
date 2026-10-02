"""Exercise the authenticated Broadcast HTTP boundary on isolated loopback."""

import json
import queue
import threading
from http.server import ThreadingHTTPServer

import httpx
import pytest
from watcher_openrouter import integration

from watcher_sdk import AsyncWatcherClient


@pytest.fixture
def receiver(monkeypatch):
    started = queue.Queue()
    seen = []

    def server(address, handler):
        instance = ThreadingHTTPServer(address, handler)
        started.put(instance)
        return instance

    def transport(request):
        seen.append(request.url.path)
        return httpx.Response(
            200, json={"granted": True, "missing": []} if request.url.path.endswith("check-permissions") else []
        )

    def client(*args, **kwargs):
        return AsyncWatcherClient(
            "http://fixture",
            httpx_client=httpx.AsyncClient(base_url="http://fixture", transport=httpx.MockTransport(transport)),
        )

    monkeypatch.setenv("OPENROUTER_WEBHOOK_TOKEN", "fixture-webhook-secret")
    monkeypatch.setenv("WATCHER_BASE_URL", "http://fixture")
    monkeypatch.setenv("WATCHER_API_KEY", "fixture-key")
    monkeypatch.setattr(integration, "ThreadingHTTPServer", server)
    monkeypatch.setattr(integration, "AsyncWatcherClient", client)
    thread = threading.Thread(
        target=integration.serve, args=("127.0.0.1", 0), kwargs={"namespace": "test"}, daemon=True
    )
    thread.start()
    instance = started.get(timeout=5)
    try:
        yield {"url": f"http://127.0.0.1:{instance.server_port}", "seen": seen}
    finally:
        instance.shutdown()
        instance.server_close()
        thread.join(timeout=5)
        assert not thread.is_alive()


@pytest.mark.parametrize("method", ["POST", "PUT"])
@pytest.mark.parametrize("payload", [{}, {"resourceSpans": []}])
def test_authenticated_connection_probe_is_not_a_submission(receiver, method, payload):
    response = httpx.request(
        method,
        receiver["url"] + "/v1/traces",
        json=payload,
        headers={"Authorization": "Bearer fixture-webhook-secret", "X-Test-Connection": "true"},
    )
    assert response.status_code == 200 and response.json()["submitted"] == 0
    assert receiver["seen"] == []


@pytest.mark.parametrize("authorization", ["", "Bearer wrong", "fixture-webhook-secret"])
def test_authentication_precedes_payload_processing(receiver, authorization):
    response = httpx.post(receiver["url"] + "/v1/traces", content=b"not-json", headers={"Authorization": authorization})
    assert response.status_code == 401 and receiver["seen"] == []


@pytest.mark.parametrize(
    "payload",
    [
        {"resourceSpans": [None]},
        {"resourceSpans": [{"scopeSpans": 7}]},
        {"resourceSpans": [{"scopeSpans": [{"spans": [None]}]}]},
    ],
)
def test_malformed_external_envelopes_are_rejected(receiver, payload):
    response = httpx.post(
        receiver["url"] + "/v1/traces",
        content=json.dumps(payload),
        headers={"Authorization": "Bearer fixture-webhook-secret"},
    )
    assert response.status_code == 422 and receiver["seen"] == []
