"""Native Aider whole-file editing waits at the injected IO boundary."""

import asyncio
import json
import threading

import httpx
import pytest
from aider.coders import Coder
from watcher_aider.observation import Capture, ObservedModel, archive_messages, run_prompt, send_capture
from watcher_aider.synchronous import EnforcedIO

from watcher_sdk import AsyncWatcherClient


@pytest.mark.parametrize(
    "decision", ["allow", "deny", "escalate", "deferred", "identity-error", "missing-outcome", "http-error", "pending"]
)
def test_native_write_waits_for_watcher(tmp_path, monkeypatch, decision):
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "greeting.txt"
    target.write_text("before native edit\n")
    requests = []
    entered, release = threading.Event(), threading.Event()

    def respond(request):
        body = json.loads(request.content)
        requests.append(body)
        enforcing = bool(body["input"]) and "settings_overrides" not in body
        if enforcing and decision == "pending":
            entered.set()
            assert release.wait(10)
        outcome = (
            decision if decision in {"deny", "escalate", "deferred"} else "deny" if decision == "pending" else "allow"
        )
        outputs = [
            {
                "tool_use_id": "wrong" if enforcing and decision == "identity-error" else call["tool_use_id"],
                "decision": outcome if enforcing else "deferred",
                "judged_decision": outcome if enforcing else "allow",
                "enforcement_mode": "enforce" if enforcing else "observe",
                "decision_source": "rule",
                "verdict": {},
                "latency_ms": 1,
            }
            for call in body["input"]
        ]
        return httpx.Response(
            503 if enforcing and decision == "http-error" else 200,
            json={"error": {"message": "fixture unavailable"}}
            if enforcing and decision == "http-error"
            else []
            if enforcing and decision == "missing-outcome"
            else outputs,
        )

    def client():
        return AsyncWatcherClient(
            httpx_client=httpx.AsyncClient(base_url="http://fixture", transport=httpx.MockTransport(respond))
        )

    capture = Capture()
    model = ObservedModel("gpt-4o", capture)
    model.extra_params = {"mock_response": "greeting.txt\n```text\nafter native edit\n```"}
    coder = Coder.create(
        main_model=model,
        edit_format="whole",
        io=EnforcedIO(capture, "native-session", client, yes=False, pretty=False),
        fnames=[str(target)],
        use_git=False,
        stream=False,
        map_tokens=0,
        auto_lint=False,
        auto_test=False,
    )
    errors = []

    def run():
        try:
            run_prompt(coder, capture, "Replace greeting.txt with after native edit.")
        except Exception as error:
            errors.append(type(error).__name__)

    if decision == "pending":
        worker = threading.Thread(target=run)
        worker.start()
        assert entered.wait(10)
        assert target.read_text() == "before native edit\n"
        release.set()
        worker.join(10)
        assert not worker.is_alive()
    else:
        run()
    assert target.read_text() == ("after native edit\n" if decision == "allow" else "before native edit\n")
    operations = [operation for exchange in capture.exchanges for operation in exchange["writes"]]
    assert operations
    assert all(operation["status"] == ("completed" if decision == "allow" else "withheld") for operation in operations)
    assert requests and "settings_overrides" not in requests[0]
    assert "before native edit" in json.dumps(requests[0]["messages"])
    model.extra_params = {"mock_response": "Native run finished"}
    run_prompt(coder, capture, "Report completion without editing files.")
    assert "Native run finished" in json.dumps(archive_messages(capture)[-1]["content"])

    async def observe():
        async with client() as watcher:
            await send_capture(watcher, "native-session", capture, record_only=True)

    asyncio.run(observe())
    assert requests[-1]["messages"] == archive_messages(capture)
