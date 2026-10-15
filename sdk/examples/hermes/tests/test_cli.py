"""The hook commands send the right Watcher requests and always print a usable Hermes directive."""

import asyncio
import json
import shlex
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from typer.testing import CliRunner
from watcher_hermes import cli
from watcher_hermes.cli import app, judge, record_session, render_hooks, watcher_client

from watcher_sdk import AsyncWatcherClient

FIXTURES = Path(__file__).parent / "fixtures"


def load(name: str) -> dict:
    """Load one captured Hermes fixture by file name."""
    return json.loads((FIXTURES / name).read_text())


def export_line(session: dict) -> str:
    """Render a session the way ``hermes sessions export -`` prints it: one JSON line."""
    return json.dumps(session) + "\n"


SESSION = load("session-terminal-read.json")
PAYLOADS = load("hook-payloads.json")
GATE_PAYLOAD = PAYLOADS["pre_tool_call"]
CALL_ID = GATE_PAYLOAD["extra"]["tool_call_id"]


def pending_session() -> dict:
    """The captured session as Hermes stores it while the first call waits: no result yet."""
    rows = SESSION["messages"]
    return {"id": SESSION["id"], "messages": rows[:2]}


def allow(tool_use_id: str = CALL_ID, **changes) -> dict:
    return {
        "tool_use_id": tool_use_id,
        "decision": "allow",
        "judged_decision": "allow",
        "enforcement_mode": "enforce",
        "decision_source": "triage",
        "verdict": {"summary": "Triage: safe"},
        "latency_ms": 1,
        **changes,
    }


def mock_client(respond, requests: list) -> AsyncWatcherClient:
    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content))
        return respond(requests[-1])

    return AsyncWatcherClient(
        httpx_client=httpx.AsyncClient(base_url="http://fixture", transport=httpx.MockTransport(handler))
    )


def test_gate_sends_full_recorded_request_in_stored_context(fake_hermes):
    requests: list = []
    hermes = fake_hermes(export_line(pending_session()))

    async def run():
        async with mock_client(lambda body: httpx.Response(200, json=[allow()]), requests) as client:
            return await judge(GATE_PAYLOAD, client, hermes_bin=hermes)

    assert asyncio.run(run()) == {}
    (body,) = requests
    assert body["mode"] == "full" and not body.get("ephemeral")
    assert body["external_ids"] == {"other": "hermes:" + SESSION["id"]}
    assert body["input"] == [
        {
            "tool_use_id": CALL_ID,
            "tool_name": "terminal",
            "tool_input": GATE_PAYLOAD["tool_input"],
            "cwd": GATE_PAYLOAD["cwd"],
        }
    ]
    assert body["messages"][-1]["tool_calls"][0]["id"] == CALL_ID
    assert "settings_overrides" not in body


def test_gate_maps_a_denial_to_a_block(fake_hermes):
    hermes = fake_hermes(export_line(pending_session()))
    denied = allow(decision="deny", judged_decision="deny", verdict={"summary": "Rule: no"})

    async def run():
        async with mock_client(lambda body: httpx.Response(200, json=[denied]), []) as client:
            return await judge(GATE_PAYLOAD, client, hermes_bin=hermes)

    assert asyncio.run(run()) == {"action": "block", "message": "Watcher denied this tool call: Rule: no"}


@pytest.mark.parametrize("response", [[], [allow(), allow()], [{"error": "boom"}]])
def test_gate_rejects_incomplete_answers(fake_hermes, response):
    hermes = fake_hermes(export_line(pending_session()))

    async def run():
        async with mock_client(lambda body: httpx.Response(200, json=response), []) as client:
            return await judge(GATE_PAYLOAD, client, hermes_bin=hermes)

    with pytest.raises((PermissionError, ValueError, KeyError, TypeError)):
        asyncio.run(run())


@pytest.mark.parametrize(
    "payload",
    [
        {**GATE_PAYLOAD, "hook_event_name": "post_tool_call"},
        {**GATE_PAYLOAD, "extra": {}},
        {**GATE_PAYLOAD, "extra": "not an object"},
        {**GATE_PAYLOAD, "tool_input": None},
        {**GATE_PAYLOAD, "session_id": ""},
    ],
)
def test_gate_refuses_payloads_without_a_named_call(payload):
    with pytest.raises(ValueError):
        cli.pending_call(payload)


def test_gate_omits_missing_cwd():
    assert cli.pending_call({**GATE_PAYLOAD, "cwd": ""})[2] is None


@pytest.mark.parametrize("value", ["0", "-1", "271", "nan", "inf"])
def test_grading_timeout_must_fit_inside_hermes_deadline(monkeypatch, value):
    monkeypatch.setenv("WATCHER_TIMEOUT_SECONDS", value)
    with pytest.raises(ValueError):
        cli.grading_timeout()


def test_grading_timeout_default(monkeypatch):
    monkeypatch.delenv("WATCHER_TIMEOUT_SECONDS", raising=False)
    assert cli.grading_timeout() == cli.DEFAULT_TIMEOUT_SECONDS


def test_record_sends_history_without_inputs(fake_hermes):
    requests: list = []
    hermes = fake_hermes(export_line(SESSION))
    payload = PAYLOADS["on_session_end"]

    async def run():
        async with mock_client(lambda body: httpx.Response(200, json=[]), requests) as client:
            await record_session(payload, client, hermes_bin=hermes)

    asyncio.run(run())
    (body,) = requests
    assert body["input"] == [] and body["external_ids"] == {"other": "hermes:" + SESSION["id"]}
    assert len(body["messages"]) == len(SESSION["messages"])


def test_record_skips_empty_sessions_and_rejects_outcomes(fake_hermes):
    requests: list = []

    async def run(session, response):
        async with mock_client(lambda body: httpx.Response(200, json=response), requests) as client:
            await record_session({"session_id": session["id"]}, client, hermes_bin=fake_hermes(export_line(session)))

    asyncio.run(run({"id": "s", "messages": []}, []))
    assert requests == []
    with pytest.raises(ValueError):
        asyncio.run(run(SESSION, [allow()]))
    with pytest.raises(ValueError):
        asyncio.run(run({"id": ""}, []))


@pytest.fixture
def patched_client(monkeypatch):
    """Route the commands' SDK client to a mock transport and return its captured requests."""
    state = SimpleNamespace(respond=lambda body: httpx.Response(200, json=[allow()]), requests=[])

    def factory(url, *, watcher_auth, state_dir):
        assert url == "http://watcher.example/api"
        return mock_client(lambda body: state.respond(body), state.requests)

    monkeypatch.setattr(cli, "watcher_client", factory)
    return state


def run_command(args, payload):
    return CliRunner().invoke(app, [*args, "--watcher-url", "http://watcher.example/api"], input=json.dumps(payload))


def test_gate_command_prints_the_directive(patched_client, fake_hermes):
    result = run_command(["gate", "--hermes-bin", fake_hermes(export_line(pending_session()))], GATE_PAYLOAD)
    assert result.exit_code == 0 and json.loads(result.stdout) == {}


def test_gate_command_blocks_on_any_failure(patched_client, fake_hermes):
    patched_client.respond = lambda body: httpx.Response(503, json={"error": {"message": "secret body"}})
    result = run_command(["gate", "--hermes-bin", fake_hermes(export_line(pending_session()))], GATE_PAYLOAD)
    assert result.exit_code == 0
    assert json.loads(result.stdout)["action"] == "block"
    assert "secret body" not in result.output


def test_gate_command_blocks_on_unreadable_stdin(patched_client):
    result = CliRunner().invoke(app, ["gate", "--watcher-url", "http://watcher.example/api"], input="not json")
    assert json.loads(result.stdout)["action"] == "block"


def test_gate_command_passes_escalate_as_block(patched_client, fake_hermes):
    patched_client.respond = lambda body: httpx.Response(
        200, json=[allow(decision="escalate", judged_decision="escalate")]
    )
    hermes = fake_hermes(export_line(pending_session()))
    asked = run_command(["gate", "--hermes-bin", hermes], GATE_PAYLOAD)
    blocked = run_command(["gate", "--hermes-bin", hermes, "--escalate-as-block"], GATE_PAYLOAD)
    assert json.loads(asked.stdout)["action"] == "approve"
    assert json.loads(blocked.stdout)["action"] == "block"


def test_record_command_never_fails_the_agent(patched_client, fake_hermes):
    patched_client.respond = lambda body: httpx.Response(200, json=[])
    ok = run_command(["record", "--hermes-bin", fake_hermes(export_line(SESSION))], PAYLOADS["on_session_end"])
    assert ok.exit_code == 0 and json.loads(ok.stdout) == {}
    patched_client.respond = lambda body: httpx.Response(500, json={"error": {"message": "secret body"}})
    failed = run_command(["record", "--hermes-bin", fake_hermes(export_line(SESSION))], PAYLOADS["on_session_end"])
    assert failed.exit_code == 0 and json.loads(failed.stdout) == {}
    assert "not confirmed recorded" in failed.stderr and "secret body" not in failed.output


def test_help_without_a_command():
    assert "gate" in CliRunner().invoke(app, []).stdout
    assert "record" in CliRunner().invoke(app, ["help"]).stdout


def test_hooks_command_prints_both_hooks():
    result = CliRunner().invoke(app, ["hooks", "--watcher-url", "https://w.example/api", "--watcher-auth"])
    assert result.exit_code == 0
    assert "pre_tool_call" in result.stdout and "on_session_end" in result.stdout
    assert "--watcher-auth" in result.stdout and "hook_callback_timeout: 300" in result.stdout


def _commands(text: str) -> dict[str, list[str]]:
    found = {}
    for line in text.splitlines():
        if "command:" in line:
            argv = shlex.split(json.loads(line.split("command:", 1)[1].strip()))
            found[argv[3]] = argv
    return found


def test_render_hooks_quotes_paths_and_scopes_modes(tmp_path):
    state = tmp_path / "watcher home"
    text = render_hooks(
        watcher_url="https://w.example/api",
        record_only=False,
        watcher_auth=True,
        watcher_state_dir=state,
        hermes_bin="/opt/my hermes/bin/hermes",
        escalate_as_block=True,
    )
    commands = _commands(text)
    assert set(commands) == {"gate", "record"}
    assert commands["gate"][-1] == "--escalate-as-block" and "--escalate-as-block" not in commands["record"]
    assert commands["gate"][commands["gate"].index("--watcher-state-dir") + 1] == str(state)
    assert commands["record"][commands["record"].index("--hermes-bin") + 1] == "/opt/my hermes/bin/hermes"
    assert "fail_closed: true" in text and "timeout: 300" in text

    record_only = render_hooks(
        watcher_url="https://w.example/api",
        record_only=True,
        watcher_auth=False,
        watcher_state_dir=None,
        hermes_bin=None,
    )
    assert set(_commands(record_only)) == {"record"} and "plugins:" not in record_only


def test_client_requires_url_and_credential_except_on_loopback(monkeypatch):
    monkeypatch.delenv("WATCHER_API_KEY", raising=False)
    with pytest.raises(ValueError):
        watcher_client(None, watcher_auth=False, state_dir=None)
    with pytest.raises(ValueError):
        watcher_client("https://w.example/api", watcher_auth=False, state_dir=None)
    assert isinstance(
        watcher_client("http://localhost:8017/api", watcher_auth=False, state_dir=None), AsyncWatcherClient
    )
    monkeypatch.setenv("WATCHER_API_KEY", "k")
    assert isinstance(watcher_client("https://w.example/api", watcher_auth=False, state_dir=None), AsyncWatcherClient)


def test_saved_sign_in_client(monkeypatch, tmp_path):
    seen = {}

    def fake(url, *, state_dir, timeout):
        seen.update(url=url, state_dir=state_dir)
        return "client"

    monkeypatch.setattr(cli, "async_client_from_watcher", fake)
    assert watcher_client("https://w.example/api", watcher_auth=True, state_dir=tmp_path) == "client"
    assert seen == {"url": "https://w.example/api", "state_dir": tmp_path}


def test_main_runs_the_app(monkeypatch):
    called = []
    monkeypatch.setattr(cli, "app", lambda: called.append(True))
    cli.main()
    assert called == [True]
