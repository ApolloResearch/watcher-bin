"""Exercise native writes and their SDK observations, including rejected outcomes."""

import asyncio
import json
from copy import deepcopy

import httpx
import pytest
from aider.coders import Coder
from watcher_aider.observation import (
    Capture,
    ObservedIO,
    ObservedModel,
    archive_messages,
    exchange_messages,
    run_prompt,
    send_capture,
)

from watcher_sdk import AsyncWatcherClient


def native_edit(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "greeting.txt"
    target.write_text("before native edit\n")
    capture = Capture()
    model = ObservedModel("gpt-4o", capture)
    model.extra_params = {"mock_response": "greeting.txt\n```text\nafter native edit\n```"}
    coder = Coder.create(
        main_model=model,
        edit_format="whole",
        io=ObservedIO(capture, yes=False, pretty=False),
        fnames=[str(target)],
        use_git=False,
        stream=False,
        map_tokens=0,
        auto_lint=False,
        auto_test=False,
    )
    run_prompt(coder, capture, "Replace the supplied file with after native edit.")
    assert target.read_text() == "after native edit\n"
    model.extra_params = {"mock_response": "finished native edit"}
    run_prompt(coder, capture, "Confirm completion without editing any file.")
    return capture, target


def test_native_edit_and_final_answer_have_original_context(tmp_path, monkeypatch):
    capture, target = native_edit(tmp_path, monkeypatch)
    assert len(capture.exchanges) == 2
    writes = [op for exchange in capture.exchanges for op in exchange["writes"]]
    assert len(writes) == 1
    assert writes[0]["arguments"] == {"path": str(target), "content": "after native edit\n"}
    assert writes[0]["status"] == "completed"
    assert "before native edit" in json.dumps(capture.exchanges[0]["request"])
    assert "after native edit" in json.dumps(capture.exchanges[1]["request"])
    messages = archive_messages(capture)
    assert messages[-1]["role"] == "assistant"
    assert "finished native edit" in json.dumps(messages[-1]["content"])
    assert [m["tool_call_id"] for m in messages if m["role"] == "tool"] == [writes[0]["id"]]
    assert capture.active is None and capture.unassociated_writes == 0


def exchange_fixture():
    return {
        "request": [{"role": "user", "content": "Change fixture"}],
        "response": {
            "choices": [{"message": {"role": "assistant", "content": "Native edit text"}, "finish_reason": "stop"}]
        },
        "writes": [],
    }


def test_native_write_error_is_preserved_and_not_success(tmp_path):
    capture = Capture(exchanges=[exchange_fixture()])
    capture.active = capture.exchanges[0]
    io = ObservedIO(capture, yes=False, pretty=False)
    with pytest.raises(IsADirectoryError):
        io.write_text(tmp_path, "never written")
    operation = capture.exchanges[0]["writes"][0]
    assert operation["status"] == "error" and operation["error"] == "IsADirectoryError"
    result = archive_messages(capture)[-1]
    assert result["tool_call_id"] == operation["id"]
    assert result["error"]["message"] == "IsADirectoryError"


def test_dry_run_does_not_claim_a_write(tmp_path):
    capture = Capture(exchanges=[exchange_fixture()])
    capture.active = capture.exchanges[0]
    target = tmp_path / "absent.txt"
    ObservedIO(capture, dry_run=True, yes=False, pretty=False).write_text(target, "absent")
    assert not target.exists() and capture.exchanges[0]["writes"] == []
    assert capture.skipped_dry_runs == 1


def test_unassociated_write_is_counted_without_invented_context(tmp_path):
    capture = Capture()
    target = tmp_path / "ordinary.txt"
    ObservedIO(capture, yes=False, pretty=False).write_text(target, "ordinary")
    assert target.read_text() == "ordinary"
    assert capture.exchanges == [] and capture.unassociated_writes == 1


@pytest.mark.parametrize("bad", [None, "paused", "wrong_id", "enforce", "grading_error", "missing"])
def test_observation_validates_outcomes_and_always_flushes(tmp_path, monkeypatch, bad):
    capture, _ = native_edit(tmp_path, monkeypatch)
    before = deepcopy(capture.exchanges)
    requests = []

    def respond(request):
        body = json.loads(request.content)
        requests.append(body)
        assert "require_recording" not in request.url.params
        if body["input"]:
            assert body["mode"] == "triage_only"
        outcomes = []
        for item in body["input"]:
            outcome = {
                "tool_use_id": item["tool_use_id"],
                "decision": "deferred",
                "judged_decision": "allow",
                "enforcement_mode": "observe",
                "decision_source": "rule",
                "verdict": {},
                "latency_ms": 1,
            }
            if bad == "paused":
                outcome.pop("judged_decision")
            if bad == "wrong_id":
                outcome["tool_use_id"] = "wrong"
            if bad == "enforce":
                outcome["enforcement_mode"] = "enforce"
            if bad == "grading_error":
                outcome["decision_source"] = "grading_error"
            if bad != "missing":
                outcomes.append(outcome)
        return httpx.Response(200, json=outcomes)

    async def exercise():
        async with AsyncWatcherClient(
            httpx_client=httpx.AsyncClient(base_url="http://watcher.invalid", transport=httpx.MockTransport(respond))
        ) as client:
            if bad:
                with pytest.raises(ValueError):
                    await send_capture(client, "native-edit", capture)
            else:
                await send_capture(client, "native-edit", capture)
                await send_capture(client, "native-edit", capture)

    asyncio.run(exercise())
    operation = capture.exchanges[0]["writes"][0]
    assert requests[0]["messages"][:-1] == exchange_messages(capture.exchanges[0])
    assert requests[0]["input"][0]["tool_use_id"] == operation["id"]
    assert "settings_overrides" not in requests[0]
    assert requests[-1]["input"] == []
    assert requests[-1]["messages"] == archive_messages(capture)
    assert "finished native edit" in json.dumps(requests[-1]["messages"][-1]["content"])
    assert capture.exchanges == before
    if not bad:
        assert requests[0]["input"] == requests[2]["input"]
