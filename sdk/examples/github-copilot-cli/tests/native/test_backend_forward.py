"""Check fixture forwarding preserves wire bytes and records the physical gate ordering."""

import importlib.util
import io
import json
from pathlib import Path

import httpx
import pytest

SPEC = importlib.util.spec_from_file_location(
    "copilot_backend_forward", Path(__file__).parent / "contained/backend_forward.py"
)
assert SPEC is not None and SPEC.loader is not None
helper = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(helper)


class Handler:
    path = "/v1/hooks/pre-tool-use"
    headers = {"Host": "fixture", "Authorization": "Bearer fixture-only", "Content-Length": "1"}

    def __init__(self):
        self.wfile = io.BytesIO()
        self.status = None
        self.sent_headers = {}

    def send_response(self, value):
        self.status = value

    def send_header(self, name, value):
        self.sent_headers[name] = value

    def end_headers(self):
        pass


def test_forward_keeps_wire_bytes_and_records_gate_before_native_effect(tmp_path, monkeypatch):
    raw = b'  {"input":{"tool_name":"Bash","tool_use_id":"call-1"},"ephemeral":false}\n'
    body = json.loads(raw)
    captured = []
    actual_client = httpx.Client

    def respond(request):
        captured.append(request)
        return httpx.Response(200, content=b'{"decision":"allow"}', headers={"Content-Type": "application/json"})

    monkeypatch.setattr(
        helper.httpx, "Client", lambda **kwargs: actual_client(**kwargs, transport=httpx.MockTransport(respond))
    )
    monkeypatch.setattr(helper, "EVIDENCE", tmp_path)
    monkeypatch.setenv("WATCHER_EXAMPLE_FORWARD_URL", "http://127.0.0.1:8123")
    monkeypatch.setenv("WATCHER_EXPECT_TOOL_EXECUTION", "1")
    handler = Handler()
    helper.forward(handler, body, raw, tmp_path / "native-effect")
    assert captured[0].content == raw
    assert captured[0].headers["Authorization"] == "Bearer fixture-only"
    assert str(captured[0].url) == "http://127.0.0.1:8123/v1/hooks/pre-tool-use"
    assert handler.status == 200 and handler.wfile.getvalue() == b'{"decision":"allow"}'
    ordering = json.loads((tmp_path / "gate-order.jsonl").read_text())
    assert ordering["tool_use_id"] == "call-1" and ordering["ephemeral"] is False
    assert not ordering["before_request"]["marker_exists"] and not ordering["after_response"]["marker_exists"]
    assert ordering["before_request"]["monotonic"] <= ordering["after_response"]["monotonic"]
    recorded = json.loads((tmp_path / "forwarded-sdk-responses.jsonl").read_text())
    assert recorded["request"] == body and recorded["status_code"] == 200


def test_forward_does_not_treat_recording_snapshots_as_gate_requests(tmp_path, monkeypatch):
    raw = b'{"input":[],"messages":[]}'
    actual_client = httpx.Client
    monkeypatch.setattr(
        helper.httpx,
        "Client",
        lambda **kwargs: actual_client(**kwargs, transport=httpx.MockTransport(lambda request: httpx.Response(200))),
    )
    monkeypatch.setattr(helper, "EVIDENCE", tmp_path)
    monkeypatch.setenv("WATCHER_EXAMPLE_FORWARD_URL", "http://127.0.0.1:8123")
    monkeypatch.setenv("WATCHER_EXPECT_TOOL_EXECUTION", "1")
    helper.forward(Handler(), json.loads(raw), raw, tmp_path / "native-effect")
    assert not (tmp_path / "gate-order.jsonl").exists()


@pytest.mark.parametrize("target", ["https://api.openai.com", "http://example.com", "http://user:secret@127.0.0.1"])
def test_forward_refuses_nonlocal_or_embedded_credentials(target, tmp_path, monkeypatch):
    monkeypatch.setenv("WATCHER_EXAMPLE_FORWARD_URL", target)
    monkeypatch.setenv("WATCHER_EXPECT_TOOL_EXECUTION", "1")
    with pytest.raises(ValueError, match="loopback"):
        helper.forward(Handler(), {}, b"{}", tmp_path / "marker")


def test_forward_requires_an_independent_expected_execution(monkeypatch):
    monkeypatch.delenv("WATCHER_EXPECT_TOOL_EXECUTION", raising=False)
    with pytest.raises(ValueError, match="0 or 1"):
        helper.expects_execution()
