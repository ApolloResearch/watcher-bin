"""Forwarding retains wire results while file-open evidence stays independent."""

import importlib.util
import io
import json
from pathlib import Path

import httpx
import pytest

HELPER_PATH = Path(__file__).parent / "native_evidence.py"
if not HELPER_PATH.exists():
    HELPER_PATH = Path(__file__).parent / "contained/native_evidence.py"
SPEC = importlib.util.spec_from_file_location("fixture_native_evidence", HELPER_PATH)
assert SPEC is not None and SPEC.loader is not None
helper = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(helper)


class Handler:
    path = "/v1/hooks/pre-tool-use"
    headers = {"Host": "fixture", "Content-Length": "1", "Authorization": "Bearer fixture-only"}

    def __init__(self):
        self.wfile = io.BytesIO()
        self.status = None
        self.sent_headers = {}

    def send_response(self, value):
        self.status = value

    def send_header(self, key, value):
        self.sent_headers[key] = value

    def end_headers(self):
        pass


@pytest.mark.parametrize("ephemeral", [False, True])
@pytest.mark.parametrize("status", [200, 503])
def test_forward_preserves_bytes_status_and_independent_effect_snapshot(tmp_path, monkeypatch, ephemeral, status):
    call = {"tool_name": "read", "tool_use_id": "pending", "tool_input": {"path": "file"}}
    body = {"input": call if ephemeral else [call], "messages": [], "ephemeral": ephemeral, "mode": "full"}
    raw = (" " + json.dumps(body) + "\n").encode()
    captured = []
    actual_client = httpx.Client

    def respond(request):
        captured.append(request)
        return httpx.Response(status, content=b'{"fixture":"original response"}')

    monkeypatch.setattr(
        helper.httpx, "Client", lambda **kw: actual_client(**kw, transport=httpx.MockTransport(respond))
    )
    monkeypatch.setattr(helper, "EVIDENCE", tmp_path)
    monkeypatch.setenv("WATCHER_EXAMPLE_FORWARD_URL", "http://127.0.0.1:8123")
    monkeypatch.setenv("WATCHER_EXPECT_TOOL_EXECUTION", "0")
    handler = Handler()
    assert helper.forward(handler, body, raw, lambda: {"file_opens": {"file": 0}})
    assert captured[0].content == raw and captured[0].headers["Authorization"] == "Bearer fixture-only"
    assert handler.status == status and handler.wfile.getvalue() == b'{"fixture":"original response"}'
    order = json.loads((tmp_path / "gate-order.jsonl").read_text())
    assert order["before_request"]["file_opens"] == order["after_response"]["file_opens"] == {"file": 0}
    assert order["before_request"]["monotonic"] <= order["after_response"]["monotonic"]
    assert order["ephemeral"] == ephemeral and order["input"] == body["input"]
    retained = json.loads((tmp_path / "forwarded-sdk-responses.jsonl").read_text())
    assert retained["request"] == body and retained["status_code"] == status


def test_completed_call_is_retrospective_and_empty_input_is_recording():
    call = {"tool_use_id": "done"}
    assert not helper.is_pending({"input": [call], "messages": [{"role": "tool", "tool_call_id": "done"}]})
    assert not helper.is_pending({"input": [], "messages": []})
    assert helper.is_pending({"input": [call], "messages": [], "mode": "full"})
    assert not helper.is_pending({"input": [call], "messages": [], "mode": "triage_only"})


@pytest.mark.parametrize("target", ["https://api.openai.com", "http://example.com", "http://user:secret@127.0.0.1"])
def test_forward_rejects_external_or_credential_targets(monkeypatch, target):
    monkeypatch.setenv("WATCHER_EXAMPLE_FORWARD_URL", target)
    monkeypatch.setenv("WATCHER_EXPECT_TOOL_EXECUTION", "1")
    with pytest.raises(ValueError, match="loopback"):
        helper.forward(Handler(), {}, b"{}", lambda: {})


def test_forward_requires_explicit_execution_oracle(monkeypatch):
    monkeypatch.setenv("WATCHER_EXAMPLE_FORWARD_URL", "http://127.0.0.1:8123")
    monkeypatch.delenv("WATCHER_EXPECT_TOOL_EXECUTION", raising=False)
    with pytest.raises(ValueError, match="0 or 1"):
        helper.expects_execution(False)


def test_files_are_counted_separately_and_driver_reads_cannot_pass_as_no_execution(tmp_path, monkeypatch):
    monkeypatch.setattr(helper, "EVIDENCE", tmp_path)
    first, second = tmp_path / "first", tmp_path / "second"
    first.write_text("one")
    second.write_text("two")
    reads = helper.FileReads([first, second])
    try:
        assert reads.snapshot()["file_opens"] == {str(first): 0, str(second): 0}
        reads.verify(False)
        assert first.read_text() == "one"
        assert reads.snapshot()["file_opens"] == {str(first): 1, str(second): 0}
        with pytest.raises(AssertionError):
            reads.verify(True)
        assert second.read_text() == "two"
        reads.verify(True)
        with pytest.raises(AssertionError):
            reads.verify(False)
    finally:
        reads.close()
