"""Exercise denial continuation end to end at the bridge: notices, alternatives, final generation, markers.

Each test drives the bridge's real HTTP handler. Watcher is the public SDK
over a mock transport. The Kong route that the bridge calls back for
alternatives is simulated faithfully: it asks the bridge's own ``/validate``
to verify the marker against the exact body, as the Lua plugin does, before
the scripted provider answers.
"""

import asyncio
import io
import json
import time
from collections.abc import Callable
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
import watcher_kong_ai.bridge as bridge
from watcher_kong_ai.alternatives import ALTERNATIVE_HEADER, marker_key, sign_marker, verify_marker
from watcher_kong_ai.notices import ALTERNATIVE_FAILED, SYSTEM_NOTICE, with_system_notice

from watcher_sdk import AsyncWatcherClient

ROUTE = "/v1/chat/completions"
TOOLS = [
    {"type": "function", "function": {"name": "Write", "parameters": {"type": "object"}}},
    {"type": "function", "function": {"name": "Read", "parameters": {"type": "object"}}},
]
CONTINUE = "Continue the user's task another way"
STOP_AFTER_CAP = "Several different approaches have now been blocked, so stop"
ASK_APPROVAL = "A. allow this call, B. skip it, C. do something else."
ASK_FIXED = "A. skip it, B. do something else, C. ask an administrator to change the policy."
SIBLING = "did not run because Watcher refused another call in the same response."


def completion(identity: str, content: str | None = None, calls: tuple = ()) -> dict:
    """A provider completion with ``calls`` given as (id, name, arguments) triples."""
    message: dict[str, Any] = {"role": "assistant", "content": content}
    if calls:
        message["tool_calls"] = [
            {"id": call_id, "type": "function", "function": {"name": name, "arguments": json.dumps(arguments)}}
            for call_id, name, arguments in calls
        ]
    return {
        "id": identity,
        "object": "chat.completion",
        "created": int(identity.rsplit("-", 1)[-1]) if identity[-1].isdigit() else 1,
        "model": "fixture",
        "usage": {"prompt_tokens": 5, "completion_tokens": 10, "total_tokens": 15},
        "choices": [{"index": 0, "message": message, "finish_reason": "tool_calls" if calls else "stop"}],
    }


def outcome(call_id: str, name: str, decision: str, source: str = "rule") -> dict:
    """A consistent enforced Watcher outcome with a public reason naming the tool."""
    value = {
        "tool_use_id": call_id,
        "decision": decision,
        "judged_decision": decision,
        "decision_source": source,
        "enforcement_mode": "enforce",
        "verdict": {"explanation": f"Fixture reason for {name}"},
        "latency_ms": 1,
    }
    if source == "grading_error":
        value["grading_error"] = {"code": "timeout", "message": "Fixture timeout"}
    return value


def by_name(decisions: dict[str, str], source: str = "rule") -> Callable[[dict], list]:
    """Decide each call by tool name; unnamed tools are allowed."""

    def decide(hook: dict) -> list:
        calls = hook["response_body"]["choices"][0]["message"].get("tool_calls") or []
        return [
            outcome(call["id"], call["function"]["name"], decisions.get(call["function"]["name"], "allow"), source)
            for call in calls
        ]

    return decide


class _Socket:
    def __init__(self, raw: bytes):
        self.raw = raw
        self.response = bytearray()

    def makefile(self, *args):
        return io.BytesIO(self.raw)

    def sendall(self, data):
        self.response.extend(data)


class Harness:
    """The bridge's real handler, a scripted provider behind a simulated Kong route, and a mock Watcher.

    ``proposals`` are returned in order, one per provider call, including
    the client's original proposal. ``provider`` records every body the
    provider received with its headers; ``watcher`` every hook submission
    that asks for decisions, and ``recordings`` the submissions that record a
    delivered replacement (those naming ``withheld_tool_use_ids``).
    """

    def __init__(
        self,
        monkeypatch,
        proposals: list[dict],
        decide: Callable[[dict], list],
        *,
        deadline: float = 30,
        gateway: Callable[[httpx.Request], Any] | None = None,
        watcher_status: Callable[[int], int] = lambda _: 200,
        recording_status: int = 200,
        old_server: bool = False,
    ):
        self.proposals = proposals
        self.recording_status = recording_status
        self.old_server = old_server
        self.rejected: list[dict] = []
        self.decide = decide
        self.provider: list[tuple[dict, dict]] = []
        self.watcher: list[dict] = []
        self.recordings: list[dict] = []
        # What the bridge had already written to the plugin when each recording arrived.
        self.sent_before_recording: list[bytes] = []
        self.connection: _Socket | None = None
        self.markers: list[str] = []
        self.watcher_status = watcher_status
        handlers = []
        monkeypatch.setattr(
            bridge,
            "ThreadingHTTPServer",
            lambda _address, handler: handlers.append(handler) or SimpleNamespace(serve_forever=lambda: None),
        )
        monkeypatch.setattr(
            bridge,
            "AsyncWatcherClient",
            lambda *args, **kwargs: AsyncWatcherClient(
                "http://watcher.invalid",
                httpx_client=httpx.AsyncClient(
                    base_url="http://watcher.invalid", transport=httpx.MockTransport(self._watcher)
                ),
            ),
        )
        real_client = httpx.AsyncClient
        monkeypatch.setattr(
            bridge,
            "httpx",
            SimpleNamespace(AsyncClient=lambda: real_client(transport=httpx.MockTransport(gateway or self._gateway))),
        )
        monkeypatch.setenv("WATCHER_BRIDGE_TOKEN", "fixture-token")
        monkeypatch.setenv("WATCHER_BASE_URL", "http://watcher.invalid")
        monkeypatch.setenv("WATCHER_API_KEY", "fixture-key")
        bridge.serve("127.0.0.1", 8765, gateway_url="http://kong.invalid", deadline_seconds=deadline)
        self.handler = handlers[0]

    def post(self, path: str, payload: dict) -> tuple[int, dict]:
        """Call the bridge as the Lua plugin does."""
        data = json.dumps(payload).encode()
        raw = (
            f"POST {path} HTTP/1.0\r\nAuthorization: Bearer fixture-token\r\nContent-Length: {len(data)}\r\n\r\n"
        ).encode() + data
        connection = _Socket(raw)
        if path == "/evaluate":
            # Nested /validate calls from the simulated route must not replace it.
            self.connection = connection
        self.handler(connection, ("127.0.0.1", 1), SimpleNamespace())
        head, body = bytes(connection.response).split(b"\r\n\r\n", 1)
        return int(head.split()[1]), json.loads(body)

    def _watcher(self, request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/auth/check-permissions":
            return httpx.Response(200, json={"granted": True, "missing": []})
        hook = json.loads(request.content)
        if self.old_server and {"withheld_tool_use_ids", "withholds_refused_calls"} & hook.keys():
            # A server that predates the gateway fields forbids them, as FastAPI reports extra fields.
            self.rejected.append(hook)
            field = "withholds_refused_calls" if "withholds_refused_calls" in hook else "withheld_tool_use_ids"
            return httpx.Response(422, json={"detail": [{"type": "extra_forbidden", "loc": ["body", field]}]})
        if hook.get("withheld_tool_use_ids"):
            self.recordings.append(hook)
            self.sent_before_recording.append(bytes(self.connection.response) if self.connection else b"")
            return httpx.Response(self.recording_status, json=self.decide(hook))
        self.watcher.append(hook)
        status = self.watcher_status(len(self.watcher))
        if status != 200:
            return httpx.Response(status, json={"detail": "fixture failure"})
        return httpx.Response(200, json=self.decide(hook))

    def _provide(self, body: dict, headers: dict) -> dict:
        self.provider.append((body, headers))
        return self.proposals[len(self.provider) - 1]

    def _gateway(self, request: httpx.Request) -> httpx.Response:
        """Kong's nested pass: verify the marker with the bridge, strip it, then call the provider."""
        assert str(request.url) == "http://kong.invalid" + ROUTE
        marker = request.headers[ALTERNATIVE_HEADER]
        self.markers.append(marker)
        status, verdict = self.post(
            "/validate", {"request_json": request.content.decode(), "alternative_marker": marker}
        )
        assert (status, verdict) == (200, {"verdict": True})
        headers = {key: value for key, value in request.headers.items() if key != ALTERNATIVE_HEADER}
        return httpx.Response(200, json=self._provide(json.loads(request.content), headers))

    def run(self, request: dict, **plugin_fields: Any) -> tuple[int, dict, Any]:
        """One client request through the plugin: validate, provider, evaluate; returns the delivered body.

        The delivered body is the decoded replacement response, or None when the
        bridge returns none (the original response is delivered unchanged).
        ``plugin_fields`` are added to the plugin's ``/evaluate`` body, such as its routing headers.
        """
        status, validated = self.post("/validate", {"request_json": json.dumps(request)})
        assert status == 200 and validated["verdict"] is True
        noticed = json.loads(validated["request_json"])
        original = self._provide(noticed, {})
        status, reply = self.post(
            "/evaluate",
            {
                "request_json": validated["request_json"],
                "response_json": json.dumps(original),
                "metadata": {"watcher_conversation_id": "kong:parent"},
                "route_path": ROUTE,
                "credential_header": "apikey",
                "credential": "client-key",
                **plugin_fields,
            },
        )
        delivered = json.loads(reply["response_json"]) if "response_json" in reply else None
        return status, reply, delivered


def client_request(**changes) -> dict:
    return {
        "model": "fixture",
        "messages": [{"role": "system", "content": "Be careful."}, {"role": "user", "content": "Write the file."}],
        "tools": TOOLS,
        **changes,
    }


def tool_results(body: dict) -> list[str]:
    """The tool results the bridge appended after the last assistant message."""
    messages = body["messages"]
    last = max(index for index, message in enumerate(messages) if message["role"] == "assistant")
    return [message["content"] for message in messages[last + 1 :]]


def test_denial_then_allowed_alternative_is_delivered_with_notice(monkeypatch):
    original = completion("cmpl-1", "I will write it.", (("call-1", "Write", {"path": "a"}),))
    alternative = completion("cmpl-2", "Reading instead.", (("call-2", "Read", {"path": "a"}),))
    harness = Harness(monkeypatch, [original, alternative], by_name({"Write": "deny"}))
    status, reply, delivered = harness.run(client_request(temperature=0.5, parallel_tool_calls=False))
    assert status == 200 and reply["verdict"] is True
    message = delivered["choices"][0]["message"]
    assert message["content"].startswith("I will write it.\n\nWATCHER NOTICE (added by Watcher")
    assert 'Watcher blocked `Write {"path": "a"}`. Reason: Fixture reason for Write.' in message["content"]
    assert message["content"].endswith("Reading instead.")
    assert message["tool_calls"] == alternative["choices"][0]["message"]["tool_calls"]
    assert delivered["choices"][0]["finish_reason"] == "tool_calls"
    assert {key: delivered[key] for key in ("id", "created", "model", "usage")} == {
        key: original[key] for key in ("id", "created", "model", "usage")
    }
    # The notice reaches the provider, Watcher's snapshot and the continuation exactly once.
    first, _ = harness.provider[0]
    assert first["messages"][1] == {"role": "system", "content": SYSTEM_NOTICE}
    assert harness.watcher[0]["request_body"] == first
    continuation, headers = harness.provider[1]
    assert sum(message.get("content") == SYSTEM_NOTICE for message in continuation["messages"]) == 1
    assert continuation["messages"][:3] == first["messages"]
    assert headers["apikey"] == "client-key" and ALTERNATIVE_HEADER not in headers
    assert continuation["temperature"] == 0.5 and continuation["parallel_tool_calls"] is False
    assert continuation["tools"] == TOOLS and "tool_choice" not in continuation
    assert continuation["stream"] is False
    [result] = tool_results(continuation)
    assert result.startswith("WATCHER NOTICE: Watcher blocked this call.") and CONTINUE in result
    # The alternative is graded once, by the outer pass, as its own exchange.
    assert len(harness.watcher) == 2
    assert harness.watcher[1]["request_body"] == continuation
    # Graded in the client's own session, so Watcher already holds the refused call's decision.
    assert [hook["external_ids"] for hook in harness.watcher] == [{"other": "kong:parent"}] * 2
    assert all(hook["withholds_refused_calls"] is True for hook in harness.watcher)


def test_allowed_and_observed_responses_are_released_unchanged(monkeypatch):
    original = completion("cmpl-1", None, (("call-1", "Write", {"path": "a"}),))

    def observe(hook):
        [value] = by_name({})(hook)
        return [{**value, "decision": "deferred", "enforcement_mode": "observe", "judged_decision": "deny"}]

    harness = Harness(monkeypatch, [original], observe)
    status, reply, delivered = harness.run(client_request())
    assert (status, reply, delivered) == (200, {"verdict": True}, None)
    assert len(harness.provider) == 1


@pytest.mark.parametrize("tools", [TOOLS, None])
def test_repeated_denials_reach_three_proposals_then_a_final_text_generation(monkeypatch, tools):
    proposals = [
        completion(f"cmpl-{index}", f"Attempt {index}.", ((f"call-{index}", "Write", {"path": str(index)}),))
        for index in range(1, 4)
    ] + [completion("cmpl-4", "Several approaches were blocked. How should I proceed?")]
    harness = Harness(monkeypatch, proposals, by_name({"Write": "deny"}))
    request = client_request() if tools else {key: value for key, value in client_request().items() if key != "tools"}
    status, _, delivered = harness.run(request)
    assert status == 200
    assert len(harness.provider) == 4 and len(harness.watcher) == 3
    final_request, _ = harness.provider[3]
    if tools:
        assert final_request["tool_choice"] == "none"
    else:
        assert "tool_choice" not in final_request
    for earlier, _ in harness.provider[1:3]:
        assert "tool_choice" not in earlier
        assert CONTINUE in tool_results(earlier)[0]
    assert STOP_AFTER_CAP in tool_results(final_request)[0]
    message = delivered["choices"][0]["message"]
    assert "tool_calls" not in message and delivered["choices"][0]["finish_reason"] == "stop"
    assert message["content"].count("WATCHER NOTICE") == 3
    assert message["content"].endswith("How should I proceed?")


@pytest.mark.parametrize(
    "source,approvable",
    [("policy_gateway", True), ("triage", True), ("rule", False), ("threshold", False), ("grading_error", False)],
)
def test_escalation_goes_straight_to_the_final_generation(monkeypatch, source, approvable):
    proposals = [
        completion("cmpl-1", None, (("call-1", "Write", {"path": "a"}),)),
        completion("cmpl-2", "Watcher needs your decision. A. ... B. ... C. ..."),
    ]
    harness = Harness(monkeypatch, proposals, by_name({"Write": "escalate"}, source))
    status, _, delivered = harness.run(client_request())
    assert status == 200
    assert len(harness.provider) == 2 and len(harness.watcher) == 1
    final_request, _ = harness.provider[1]
    assert final_request["tool_choice"] == "none"
    [result] = tool_results(final_request)
    content = delivered["choices"][0]["message"]["content"]
    assert content.startswith("WATCHER ESCALATION (added by Watcher")
    if approvable:
        assert ASK_APPROVAL in result and "needs the user's decision before it can run" in content
        assert ASK_FIXED not in result
    else:
        assert ASK_FIXED in result and "allow this call" not in result
        assert "cannot be approved in this conversation" in content
    assert "tool_calls" not in delivered["choices"][0]["message"]
    assert delivered["choices"][0]["finish_reason"] == "stop"


@pytest.mark.parametrize("source,offers_allow", [("policy_gateway", True), ("rule", False)])
def test_final_generation_calls_are_withheld_unevaluated(monkeypatch, source, offers_allow):
    proposals = [
        completion("cmpl-1", None, (("call-1", "Write", {"path": "a"}),)),
        completion("cmpl-2", "Trying anyway.", (("call-2", "Read", {"path": "b"}),)),
    ]
    harness = Harness(monkeypatch, proposals, by_name({"Write": "escalate"}, source))
    status, _, delivered = harness.run(client_request())
    assert status == 200
    assert len(harness.watcher) == 1, "Watcher must not be asked about the final generation's calls"
    message = delivered["choices"][0]["message"]
    assert "tool_calls" not in message and delivered["choices"][0]["finish_reason"] == "stop"
    assert "Trying anyway." in message["content"]
    assert message["content"].endswith(
        "or C to do something else." if offers_allow else "or C to ask an administrator to change the policy."
    )
    assert ("Reply A to allow" in message["content"]) is offers_allow


def test_repeated_refused_operation_under_a_new_id_is_refused_without_grading(monkeypatch):
    proposals = [
        completion("cmpl-1", None, (("call-1", "Write", {"path": "a"}),)),
        completion("cmpl-2", None, (("call-renamed", "Write", {"path": "a"}),)),
        completion("cmpl-3", "Reading.", (("call-3", "Read", {"path": "a"}),)),
    ]
    harness = Harness(monkeypatch, proposals, by_name({"Write": "deny"}))
    status, _, delivered = harness.run(client_request())
    assert status == 200 and len(harness.provider) == 3
    assert len(harness.watcher) == 2
    assert [hook["response_body"]["id"] for hook in harness.watcher] == ["cmpl-1", "cmpl-3"]
    assert delivered["choices"][0]["message"]["content"].count("Watcher blocked `Write") == 2
    assert delivered["choices"][0]["message"]["tool_calls"][0]["id"] == "call-3"


def test_sibling_results_then_repeat_then_text_alternative(monkeypatch):
    proposals = [
        completion("cmpl-1", None, (("call-1", "Write", {"path": "a"}), ("call-2", "Read", {"path": "a"}))),
        completion("cmpl-2", None, (("call-3", "Write", {"path": "a"}),)),
    ]
    decide = by_name({"Write": "deny"})
    harness = Harness(monkeypatch, [*proposals, completion("cmpl-3", "Asking.")], decide)
    status, _, delivered = harness.run(client_request())
    assert status == 200
    # The repeat is refused locally; the text-only alternative is still recorded.
    assert [hook["response_body"]["id"] for hook in harness.watcher] == ["cmpl-1", "cmpl-3"]
    assert len(harness.provider) == 3
    [first_write, read_sibling] = tool_results(harness.provider[1][0])
    assert CONTINUE in first_write and read_sibling == f"This call {SIBLING}"
    assert harness.provider[2][0].get("tool_choice") is None
    assert delivered["choices"][0]["message"]["content"].endswith("Asking.")
    # Watcher never graded the repeat, so it grades the text alternative without it: shown with
    # its refusal receipt, the repeat would be recorded as a call that ran. The model still saw it.
    shown, graded = harness.provider[2][0]["messages"], harness.watcher[1]["request_body"]["messages"]
    repeat = [message for message in shown if "call-3" in json.dumps(message)]
    assert len(repeat) == 2 and graded == [message for message in shown if message not in repeat]
    assert harness.recordings[0]["withheld_tool_use_ids"] == ["call-1", "call-2", "call-3"]


def test_mixed_siblings_are_withheld_together(monkeypatch):
    proposals = [
        completion("cmpl-1", None, (("call-1", "Write", {"path": "a"}), ("call-2", "Read", {"path": "b"}))),
        completion("cmpl-2", "Done differently.", (("call-3", "Read", {"path": "c"}),)),
    ]
    harness = Harness(monkeypatch, proposals, by_name({"Write": "deny"}))
    status, _, delivered = harness.run(client_request())
    assert status == 200
    content = delivered["choices"][0]["message"]["content"]
    assert (
        f'WATCHER NOTICE (added by Watcher, not written by the assistant): `Read {{"path": "b"}}` {SIBLING}' in content
    )
    assert [call["id"] for call in delivered["choices"][0]["message"]["tool_calls"]] == ["call-3"]
    results = tool_results(harness.provider[1][0])
    assert results[0].startswith("WATCHER NOTICE: Watcher blocked this call.")
    assert results[1] == f"This call {SIBLING}"


def test_forced_tool_choice_is_kept_on_non_final_alternatives(monkeypatch):
    forced = {"type": "function", "function": {"name": "Write"}}
    proposals = [
        completion("cmpl-1", None, (("call-1", "Write", {"path": "a"}),)),
        completion("cmpl-2", None, (("call-2", "Write", {"path": "b"}),)),
        completion("cmpl-3", None, (("call-3", "Write", {"path": "c"}),)),
        completion("cmpl-4", "Stopping."),
    ]
    harness = Harness(monkeypatch, proposals, by_name({"Write": "deny"}))
    harness.run(client_request(tool_choice=forced))
    assert [body.get("tool_choice") for body, _ in harness.provider] == [forced, forced, forced, "none"]


@pytest.mark.parametrize(
    "failure,sentence",
    [
        ("provider", "No alternative was delivered because the provider did not return a reply."),
        ("watcher", "No alternative was delivered because Watcher did not evaluate the alternative."),
        ("unverified", "No alternative was delivered because Watcher's decisions do not match the alternative."),
        ("malformed", "No alternative was delivered because the gateway cannot verify the alternative."),
    ],
)
def test_failures_mid_recovery_end_with_a_fixed_sentence_and_no_calls(monkeypatch, failure, sentence):
    original = completion("cmpl-1", None, (("call-1", "Write", {"path": "a"}),))
    alternative = completion("cmpl-2", "Alternative.", (("call-2", "Read", {"path": "a"}),))
    if failure == "malformed":
        alternative["choices"][0]["finish_reason"] = "length"
    gateway = (lambda request: httpx.Response(500, json={"error": "fixture"})) if failure == "provider" else None

    def decide(hook):
        values = by_name({"Write": "deny"})(hook)
        if failure == "unverified" and hook["response_body"]["id"] == "cmpl-2":
            return [{**value, "tool_use_id": "unknown"} for value in values]
        return values

    harness = Harness(
        monkeypatch,
        [original, alternative],
        decide,
        gateway=gateway,
        watcher_status=(lambda number: 503 if number == 2 else 200) if failure == "watcher" else (lambda _: 200),
    )
    status, _, delivered = harness.run(client_request())
    assert status == 200
    message = delivered["choices"][0]["message"]
    assert "tool_calls" not in message and delivered["choices"][0]["finish_reason"] == "stop"
    assert message["content"].startswith("WATCHER NOTICE (added by Watcher")
    assert message["content"].endswith(f"{sentence}\n\n{ALTERNATIVE_FAILED}")
    assert "Alternative." not in message["content"]


@pytest.mark.parametrize("outcome", ["approved", "escalated"])
def test_reply_over_the_size_limit_is_shortened_and_still_asks(monkeypatch, outcome):
    from watcher_kong_ai import alternatives

    original = completion("cmpl-1", None, (("call-1", "Write", {"path": "a"}),))
    calls = (("call-2", "Read", {"path": "a"}),) if outcome == "approved" else ()
    # The reply fits the gateway's limit on its own, so it is generated (and,
    # if it has calls, graded); only the composed response exceeds the limit.
    reply = completion("cmpl-2", "", calls)
    reply["choices"][0]["message"]["content"] = "x" * (alternatives.MAX_BODY - len(json.dumps(reply)) - 100)
    harness = Harness(
        monkeypatch,
        [original, reply],
        by_name({"Write": "escalate" if outcome == "escalated" else "deny"}, "policy_gateway"),
    )
    status, _, delivered = harness.run(client_request())
    assert status == 200 and len(harness.provider) == 2
    assert len(harness.watcher) == (2 if outcome == "approved" else 1), "a final reply is never graded"
    message = delivered["choices"][0]["message"]
    assert "tool_calls" not in message and delivered["choices"][0]["finish_reason"] == "stop"
    assert "xxxx" not in message["content"] and len(json.dumps(delivered)) < 4096
    if outcome == "approved":
        assert message["content"] == f"{alternatives._TOO_LARGE}\n\n{ALTERNATIVE_FAILED}"
        # The approved call was dropped with the alternative, so it is withheld too.
        assert harness.recordings[0]["withheld_tool_use_ids"] == ["call-1", "call-2"]
    else:
        assert message["content"].startswith(f"{alternatives._TOO_LARGE}\n\nWATCHER ESCALATION")
        assert "Reply A to allow the escalated call" in message["content"]


def test_reply_over_the_plugins_configured_limit_is_shortened_and_still_asks(monkeypatch):
    from watcher_kong_ai import alternatives

    original = completion("cmpl-1", None, (("call-1", "Write", {"path": "a"}),))
    alternative = completion("cmpl-2", "y" * 3000, (("call-2", "Read", {"path": "a"}),))
    harness = Harness(monkeypatch, [original, alternative], by_name({"Write": "deny"}))
    status, _, delivered = harness.run(client_request(), max_body_bytes=2048)
    assert status == 200 and len(harness.watcher) == 2
    message = delivered["choices"][0]["message"]
    assert "tool_calls" not in message and message["content"] == f"{alternatives._TOO_LARGE}\n\n{ALTERNATIVE_FAILED}"
    assert harness.recordings[0]["withheld_tool_use_ids"] == ["call-1", "call-2"]


def test_reply_the_plugin_will_refuse_is_not_recorded_as_delivered(monkeypatch):
    """The original's own text keeps even the short notice over the limit; the plugin answers 403 instead."""
    original = completion("cmpl-1", "z" * 3000, (("call-1", "Write", {"path": "a"}),))
    alternative = completion("cmpl-2", "Reading.", (("call-2", "Read", {"path": "a"}),))
    harness = Harness(monkeypatch, [original, alternative], by_name({"Write": "deny"}))
    status, reply, _ = harness.run(client_request(), max_body_bytes=2048)
    assert status == 200 and len(reply["response_json"].encode()) > 2048
    assert harness.recordings == []


@pytest.mark.parametrize("limit", [1023, 8 * 1024 * 1024 + 1, "big", True])
def test_invalid_configured_limit_withholds_the_response(monkeypatch, limit):
    original = completion("cmpl-1", None, (("call-1", "Write", {"path": "a"}),))
    harness = Harness(monkeypatch, [original], by_name({"Write": "deny"}))
    _, reply, delivered = harness.run(client_request(), max_body_bytes=limit)
    assert reply["verdict"] is not True and delivered is None


@pytest.mark.parametrize(
    "content,finish",
    [(None, "stop"), ("", "stop"), (" \t\n", "stop"), ("Partial ans", "length"), ("Hidden", "content_filter")],
)
def test_text_only_alternative_that_asks_nothing_ends_with_the_question(monkeypatch, content, finish):
    original = completion("cmpl-1", "Writing.", (("call-1", "Write", {"path": "a"}),))
    alternative = completion("cmpl-2", content, ())
    alternative["choices"][0]["finish_reason"] = finish
    harness = Harness(monkeypatch, [original, alternative], by_name({"Write": "deny"}))
    status, _, delivered = harness.run(client_request())
    assert status == 200
    message = delivered["choices"][0]["message"]
    assert "tool_calls" not in message and delivered["choices"][0]["finish_reason"] == "stop"
    if finish == "stop":
        assert message["content"].startswith("Writing.\n\nWATCHER NOTICE")
        assert message["content"].endswith(f"\n\n{ALTERNATIVE_FAILED}") and len(harness.watcher) == 2
    else:
        # A cut-off alternative is refused as unverifiable, so its text is dropped.
        assert message["content"].endswith(
            f"No alternative was delivered because the gateway cannot verify the alternative.\n\n{ALTERNATIVE_FAILED}"
        )


def test_complete_text_only_alternative_is_delivered_without_the_question(monkeypatch):
    original = completion("cmpl-1", "Writing.", (("call-1", "Write", {"path": "a"}),))
    alternative = completion("cmpl-2", "I can't do that safely; shall I skip it?", ())
    harness = Harness(monkeypatch, [original, alternative], by_name({"Write": "deny"}))
    _, _, delivered = harness.run(client_request())
    content = delivered["choices"][0]["message"]["content"]
    assert content.endswith("shall I skip it?") and ALTERNATIVE_FAILED not in content


def test_deadline_exhaustion_withholds_the_late_alternative(monkeypatch):
    original = completion("cmpl-1", None, (("call-1", "Write", {"path": "a"}),))

    async def slow(request):
        await asyncio.sleep(2)
        return httpx.Response(200, json=completion("cmpl-2", None, (("call-2", "Read", {"path": "a"}),)))

    harness = Harness(monkeypatch, [original], by_name({"Write": "deny"}), deadline=0.3, gateway=slow)
    started = time.monotonic()
    status, _, delivered = harness.run(client_request())
    assert time.monotonic() - started < 1.5
    assert status == 200
    message = delivered["choices"][0]["message"]
    assert "tool_calls" not in message
    assert message["content"].endswith(
        f"No alternative was delivered because the time limit was reached.\n\n{ALTERNATIVE_FAILED}"
    )


def test_original_watcher_failure_still_withholds(monkeypatch):
    original = completion("cmpl-1", None, (("call-1", "Write", {"path": "a"}),))
    harness = Harness(monkeypatch, [original], by_name({}), watcher_status=lambda _: 503)
    status, reply, delivered = harness.run(client_request())
    assert (status, reply, delivered) == (503, {"verdict": False}, None)
    assert len(harness.provider) == 1


def test_validate_adds_the_notice_once_after_leading_instructions(monkeypatch):
    harness = Harness(monkeypatch, [], by_name({}))
    request = {
        "model": "fixture",
        "messages": [
            {"role": "system", "content": "One."},
            {"role": "developer", "content": "Two."},
            {"role": "user", "content": "Hi"},
            {"role": "system", "content": "Later."},
        ],
    }
    _, validated = harness.post("/validate", {"request_json": json.dumps(request)})
    noticed = json.loads(validated["request_json"])
    assert [message["content"] for message in noticed["messages"]] == ["One.", "Two.", SYSTEM_NOTICE, "Hi", "Later."]
    raw = validated["request_json"]
    assert harness.post("/validate", {"request_json": raw}) == (200, {"verdict": True, "request_json": raw})


@pytest.mark.parametrize(
    "messages,expected",
    [
        ([{"role": "user", "content": "Hi"}], 0),
        ([{"role": "system", "content": "A"}, {"role": "user", "content": "Hi"}], 1),
        ([{"role": "system", "content": [{"type": "text", "text": SYSTEM_NOTICE}]}], None),
        ([{"role": "user", "content": "Hi"}, {"role": "system", "content": SYSTEM_NOTICE}], 0),
        ("not a list", None),
    ],
)
def test_system_notice_position_and_idempotency(messages, expected):
    noticed = with_system_notice({"model": "fixture", "messages": messages})
    if expected is None:
        assert noticed is None
    else:
        assert noticed is not None
        assert noticed["messages"][expected] == {"role": "system", "content": SYSTEM_NOTICE}
        assert len(noticed["messages"]) == len(messages) + 1


def test_alternative_marker_binds_key_body_and_expiry(monkeypatch):
    harness = Harness(monkeypatch, [], by_name({}))
    body = json.dumps(client_request())
    key = marker_key("fixture-key")
    future = int(time.time()) + 60
    valid = sign_marker(key, body.encode(), future)
    assert harness.post("/validate", {"request_json": body, "alternative_marker": valid}) == (200, {"verdict": True})
    for marker in [
        "forged",
        "1.abc",
        f"{future}.{'0' * 64}",
        sign_marker(key, body.encode(), int(time.time()) - 5),
        sign_marker(key, (body + " ").encode(), future),
        sign_marker(marker_key("other-key"), body.encode(), future),
        valid.upper(),
    ]:
        assert harness.post("/validate", {"request_json": body, "alternative_marker": marker}) == (
            200,
            {"verdict": False},
        ), marker
    assert not verify_marker(key, valid, body.encode(), now=future + 1)


UNUSABLE_ROUTES = [
    {"route_path": "https://elsewhere.invalid/x"},
    {"route_path": "/v1/../admin"},
    {"credential_header": "x-watcher-alternative"},
    {"credential_header": "bad header"},
    {"route_host": "tenant.example\r\nx-injected: 1"},
    {"route_host": 5},
    {"route_headers": {"x-watcher-alternative": "1"}},
    {"route_headers": {"apikey": "other-key"}},
    {"route_headers": {"host": "elsewhere.example"}},
    {"route_headers": {"content-type": "text/plain"}},
    {"route_headers": {"x-tenant": "a\nb"}},
    {"route_headers": {"x-tenant": 1}},
    {"route_headers": ["x-tenant"]},
    {"route_headers": {f"x-h{index}": "v" for index in range(17)}},
]


@pytest.mark.parametrize("fields", UNUSABLE_ROUTES)
def test_unusable_route_ends_recovery_without_blocking_evaluation(monkeypatch, fields):
    original = completion("cmpl-1", "Writing.", (("call-1", "Write", {"path": "a"}),))
    harness = Harness(monkeypatch, [original], by_name({"Write": "deny"}))
    status, reply, delivered = harness.run(client_request(), **fields)
    assert status == 200 and reply["verdict"] is True
    assert len(harness.watcher) == 1 and len(harness.provider) == 1
    message = delivered["choices"][0]["message"]
    assert "tool_calls" not in message and delivered["choices"][0]["finish_reason"] == "stop"
    assert message["content"].startswith("Writing.\n\nWATCHER NOTICE")
    assert message["content"].endswith(
        "No alternative was delivered because the gateway cannot send an alternative to the client's route."
        f"\n\n{ALTERNATIVE_FAILED}"
    )


@pytest.mark.parametrize("fields", UNUSABLE_ROUTES)
def test_unusable_route_still_releases_allowed_responses(monkeypatch, fields):
    original = completion("cmpl-1", None, (("call-1", "Read", {"path": "a"}),))
    harness = Harness(monkeypatch, [original], by_name({}))
    assert harness.run(client_request(), **fields) == (200, {"verdict": True}, None)
    assert len(harness.watcher) == 1


@pytest.mark.parametrize("gateway_url", [None, "", "ftp://kong.invalid", "kong.invalid:8000"])
def test_serve_requires_a_gateway_url_after_the_credential_check(monkeypatch, gateway_url):
    checked = []

    def transport(request):
        checked.append(request.url.path)
        return httpx.Response(200, json={"granted": True, "missing": []})

    monkeypatch.setattr(bridge, "ThreadingHTTPServer", lambda *_: pytest.fail("The bridge must not listen"))
    monkeypatch.setattr(
        bridge,
        "AsyncWatcherClient",
        lambda *args, **kwargs: AsyncWatcherClient(
            "http://watcher.invalid",
            httpx_client=httpx.AsyncClient(base_url="http://watcher.invalid", transport=httpx.MockTransport(transport)),
        ),
    )
    monkeypatch.setenv("WATCHER_BRIDGE_TOKEN", "fixture-token")
    monkeypatch.setenv("WATCHER_BASE_URL", "http://watcher.invalid")
    monkeypatch.setenv("WATCHER_API_KEY", "fixture-key")
    with pytest.raises(ValueError, match="--gateway-url"):
        bridge.serve("127.0.0.1", 8765, gateway_url=gateway_url, deadline_seconds=30)
    assert checked == ["/v1/auth/check-permissions"]


def test_alternative_keeps_the_routing_headers(monkeypatch):
    proposals = [
        completion("cmpl-1", None, (("call-1", "Write", {"path": "a"}),)),
        completion("cmpl-2", "Reading.", (("call-2", "Read", {"path": "a"}),)),
    ]
    harness = Harness(monkeypatch, proposals, by_name({"Write": "deny"}))
    status, _, delivered = harness.run(
        client_request(), route_host="tenant-b.example:8000", route_headers={"X-Tenant": "b"}
    )
    assert status == 200 and delivered["choices"][0]["message"]["tool_calls"][0]["id"] == "call-2"
    _, headers = harness.provider[1]
    assert headers["host"] == "tenant-b.example:8000"
    assert headers["x-tenant"] == "b" and headers["apikey"] == "client-key"


@pytest.mark.parametrize("content_type", ["application/json", "Application/JSON; charset=utf-8"])
def test_json_content_type_predicate_is_sent_as_the_client_sent_it(monkeypatch, content_type):
    proposals = [
        completion("cmpl-1", None, (("call-1", "Write", {"path": "a"}),)),
        completion("cmpl-2", "Reading.", (("call-2", "Read", {"path": "a"}),)),
    ]
    harness = Harness(monkeypatch, proposals, by_name({"Write": "deny"}))
    status, _, delivered = harness.run(client_request(), route_headers={"Content-Type": content_type})
    assert status == 200 and delivered["choices"][0]["message"]["tool_calls"][0]["id"] == "call-2"
    assert harness.provider[1][1]["content-type"] == content_type


@pytest.mark.parametrize(
    "content,finish",
    [
        (None, "stop"),
        ("", "stop"),
        ("   ", "stop"),
        ("I was going to ask whether", "length"),
        ("Should I", "content_filter"),
        ("Both writes were blocked, so I stopped.", "stop"),
    ],
    ids=["null", "empty", "blank", "cut-off", "filtered", "no-question"],
)
def test_unanswered_final_reply_ends_with_the_stop_notice(monkeypatch, content, finish):
    final = completion("cmpl-2", content)
    final["choices"][0]["finish_reason"] = finish
    proposals = [completion("cmpl-1", "Writing.", (("call-1", "Write", {"path": "a"}),)), final]
    harness = Harness(monkeypatch, proposals, by_name({"Write": "escalate"}, "policy_gateway"))
    status, _, delivered = harness.run(client_request())
    assert status == 200 and len(harness.watcher) == 1
    choice = delivered["choices"][0]
    assert "tool_calls" not in choice["message"] and choice["finish_reason"] == "stop"
    assert choice["message"]["content"].startswith("Writing.\n\nWATCHER ESCALATION")
    assert choice["message"]["content"].endswith("B to skip it, or C to do something else.")
    if content and content.strip():
        assert content in choice["message"]["content"]


def test_answered_final_reply_has_no_stop_notice(monkeypatch):
    """A complete final reply that asks in its own words is not asked twice."""
    asking = "Should I? A. allow this call, B. skip it, C. do something else."
    proposals = [
        completion("cmpl-1", None, (("call-1", "Write", {"path": "a"}),)),
        completion("cmpl-2", asking),
    ]
    harness = Harness(monkeypatch, proposals, by_name({"Write": "escalate"}, "policy_gateway"))
    _, _, delivered = harness.run(client_request())
    content = delivered["choices"][0]["message"]["content"]
    assert content.endswith(asking) and "Watcher withheld further tool calls" not in content


def truncated_final() -> dict:
    """A final reply cut off by the length limit inside a tool call's arguments."""
    final = completion("cmpl-final", "Partial question for", (("call-final", "Read", {}),))
    final["choices"][0]["message"]["tool_calls"][0]["function"]["arguments"] = '{"path":'
    final["choices"][0]["finish_reason"] = "length"
    return final


@pytest.mark.parametrize("trigger", ["policy_gateway escalation", "three-refusal cap"])
def test_truncated_final_call_is_withheld_unparsed_and_the_user_is_asked(monkeypatch, trigger):
    if trigger == "three-refusal cap":
        refused = [
            completion(f"cmpl-{index}", None, ((f"call-{index}", "Write", {"path": str(index)}),))
            for index in range(1, 4)
        ]
        harness = Harness(monkeypatch, [*refused, truncated_final()], by_name({"Write": "deny"}))
        ending, graded, calls = "How would you like to proceed?", 3, 4
    else:
        original = completion("cmpl-1", None, (("call-1", "Write", {"path": "a"}),))
        harness = Harness(monkeypatch, [original, truncated_final()], by_name({"Write": "escalate"}, "policy_gateway"))
        ending, graded, calls = "B to skip it, or C to do something else.", 1, 2
    status, _, delivered = harness.run(client_request())
    assert status == 200
    assert len(harness.watcher) == graded and len(harness.provider) == calls
    choice = delivered["choices"][0]
    assert "tool_calls" not in choice["message"] and choice["finish_reason"] == "stop"
    content = choice["message"]["content"]
    assert "Partial question for" in content and content.endswith(ending)
    assert "No final reply was delivered" not in content


@pytest.mark.parametrize("failure", ["provider", "slow", "unreadable"])
def test_failed_final_generation_still_asks_the_user(monkeypatch, failure):
    original = completion("cmpl-1", "Writing.", (("call-1", "Write", {"path": "a"}),))

    async def gateway(request):
        if failure == "slow":
            await asyncio.sleep(2)
        if failure == "unreadable":
            return httpx.Response(200, content=b"not json")
        return httpx.Response(500, json={"error": "fixture"})

    harness = Harness(monkeypatch, [original], by_name({"Write": "escalate"}, "rule"), gateway=gateway, deadline=0.5)
    status, _, delivered = harness.run(client_request())
    assert status == 200 and len(harness.watcher) == 1
    choice = delivered["choices"][0]
    assert "tool_calls" not in choice["message"] and choice["finish_reason"] == "stop"
    reason = "the time limit was reached" if failure == "slow" else "the provider did not return a reply"
    assert f"No final reply was delivered because {reason}.\n\nWATCHER ESCALATION" in choice["message"]["content"]
    assert choice["message"]["content"].endswith("or C to ask an administrator to change the policy.")


def test_unusable_route_after_an_escalation_still_asks_the_user(monkeypatch):
    original = completion("cmpl-1", None, (("call-1", "Write", {"path": "a"}),))
    harness = Harness(monkeypatch, [original], by_name({"Write": "escalate"}, "triage"))
    _, _, delivered = harness.run(client_request(), route_headers={"content-type": "text/plain"})
    content = delivered["choices"][0]["message"]["content"]
    assert "No final reply was delivered because the gateway cannot send an alternative" in content
    assert content.endswith("B to skip it, or C to do something else.")


@pytest.mark.parametrize(
    "response_format",
    [{"type": "json_object"}, {"type": "json_schema", "json_schema": {"name": "answer", "schema": {}}}],
)
@pytest.mark.parametrize("decision", ["deny", "escalate"])
def test_structured_output_refusal_is_an_explicit_error(monkeypatch, response_format, decision):
    original = completion("cmpl-1", '{"answer": 1}', (("call-1", "Write", {"path": "a"}),))
    harness = Harness(monkeypatch, [original], by_name({"Write": decision}))
    status, reply, delivered = harness.run(client_request(response_format=response_format))
    assert status == 200 and reply["verdict"] is True and reply["status"] == 403
    assert delivered == {
        "error": {
            "message": "Watcher refused a tool call in this response, and its notice cannot be delivered "
            "inside the requested structured output format",
            "type": "watcher_withheld",
            "code": 403,
        }
    }
    assert len(harness.watcher) == 1 and len(harness.provider) == 1 and harness.markers == []


@pytest.mark.parametrize("response_format", [{"type": "text"}, None])
def test_text_response_format_still_gets_the_notice(monkeypatch, response_format):
    proposals = [
        completion("cmpl-1", None, (("call-1", "Write", {"path": "a"}),)),
        completion("cmpl-2", "Reading.", (("call-2", "Read", {"path": "a"}),)),
    ]
    harness = Harness(monkeypatch, proposals, by_name({"Write": "deny"}))
    request = client_request(response_format=response_format) if response_format else client_request()
    status, reply, delivered = harness.run(request)
    assert status == 200 and "status" not in reply
    assert delivered["choices"][0]["message"]["content"].startswith("WATCHER NOTICE")
    assert len(harness.provider) == 2


def test_structured_output_allowed_response_is_released_unchanged(monkeypatch):
    original = completion("cmpl-1", '{"answer": 1}', (("call-1", "Read", {"path": "a"}),))
    harness = Harness(monkeypatch, [original], by_name({}))
    assert harness.run(client_request(response_format={"type": "json_object"})) == (200, {"verdict": True}, None)


def test_recovered_reply_is_recorded_naming_every_withheld_call(monkeypatch):
    """The refused call and its sibling are named; the released call moves into history unevaluated."""
    original = completion("cmpl-1", None, (("call-1", "Write", {"path": "a"}), ("call-2", "Read", {"path": "b"})))
    alternative = completion("cmpl-2", "Reading instead.", (("call-3", "Read", {"path": "c"}),))
    harness = Harness(monkeypatch, [original, alternative], by_name({"Write": "deny"}))
    status, _, delivered = harness.run(client_request())
    assert status == 200 and len(harness.watcher) == 2
    [recording] = harness.recordings
    assert recording["withheld_tool_use_ids"] == ["call-1", "call-2"]
    assert recording["withholds_refused_calls"] is True and recording["external_ids"] == {"other": "kong:parent"}
    # The plugin had the whole reply before the recording was sent.
    [sent] = harness.sent_before_recording
    assert json.loads(sent.split(b"\r\n\r\n", 1)[1])["response_json"] == json.dumps(delivered, ensure_ascii=False)
    assert recording["request_body"]["messages"][-1] == delivered["choices"][0]["message"]
    assert recording["request_body"]["messages"][:-1] == harness.watcher[0]["request_body"]["messages"]
    reply = recording["response_body"]["choices"][0]
    assert reply["message"] == {"role": "assistant", "content": None} and reply["finish_reason"] == "stop"


def test_text_reply_is_recorded_as_delivered_and_a_reused_id_is_not_named(monkeypatch):
    """A delivered call keeps its ID out of the withheld list even when a refused proposal used it first."""
    original = completion("cmpl-1", None, (("call-1", "Write", {"path": "a"}),))
    reused = completion("cmpl-2", None, (("call-1", "Read", {"path": "a"}),))
    harness = Harness(monkeypatch, [original, reused], by_name({"Write": "deny"}))
    _, _, delivered = harness.run(client_request())
    assert delivered["choices"][0]["message"]["tool_calls"][0]["id"] == "call-1"
    assert harness.recordings == [], "nothing was withheld that the client did not receive"

    text = completion("cmpl-3", "I will stop here.")
    harness = Harness(monkeypatch, [original, text], by_name({"Write": "deny"}))
    _, _, delivered = harness.run(client_request())
    [recording] = harness.recordings
    assert recording["response_body"] == delivered and recording["withheld_tool_use_ids"] == ["call-1"]
    assert recording["request_body"] == harness.watcher[0]["request_body"]


def test_unverified_alternative_calls_are_named_and_final_calls_are_not(monkeypatch):
    original = completion("cmpl-1", None, (("call-1", "Write", {"path": "a"}),))
    alternative = completion("cmpl-2", None, (("call-2", "Read", {"path": "a"}),))

    def mismatched(hook: dict) -> list:
        if hook["response_body"]["id"] == "cmpl-2":
            return [outcome("call-other", "Read", "allow")]
        return by_name({"Write": "deny"})(hook)

    harness = Harness(monkeypatch, [original, alternative], mismatched)
    harness.run(client_request())
    assert harness.recordings[0]["withheld_tool_use_ids"] == ["call-1", "call-2"]

    final = completion("cmpl-2", "Should I?", (("call-9", "Read", {}),))
    harness = Harness(monkeypatch, [original, final], by_name({"Write": "escalate"}, "policy_gateway"))
    harness.run(client_request())
    assert harness.recordings[0]["withheld_tool_use_ids"] == ["call-1"], "Watcher never saw the final reply's calls"


def test_failed_recording_does_not_change_the_delivered_reply(monkeypatch):
    original = completion("cmpl-1", None, (("call-1", "Write", {"path": "a"}),))
    text = completion("cmpl-2", "I will stop here.")
    # Each harness patches the bridge module, so they run one after the other.
    expected = Harness(monkeypatch, [original, text], by_name({"Write": "deny"})).run(client_request())
    failing = Harness(monkeypatch, [original, text], by_name({"Write": "deny"}), recording_status=503)
    assert failing.run(client_request()) == expected
    assert len(failing.recordings) == 1


def test_older_watcher_without_the_gateway_fields_still_decides_and_records(monkeypatch):
    original = completion("cmpl-1", None, (("call-1", "Write", {"path": "a"}),))
    alternative = completion("cmpl-2", "Reading instead.", (("call-2", "Read", {"path": "a"}),))
    harness = Harness(monkeypatch, [original, alternative], by_name({"Write": "deny"}), old_server=True)
    status, _, delivered = harness.run(client_request())
    assert status == 200 and delivered["choices"][0]["message"]["tool_calls"][0]["id"] == "call-2"
    # Two evaluations and the recording were each rejected once, then sent again without the fields.
    assert len(harness.rejected) == 3 and len(harness.watcher) == 3
    assert not any({"withheld_tool_use_ids", "withholds_refused_calls"} & hook.keys() for hook in harness.watcher)


def test_unrelated_watcher_validation_error_is_not_retried(monkeypatch):
    original = completion("cmpl-1", None, (("call-1", "Write", {"path": "a"}),))
    harness = Harness(monkeypatch, [original], by_name({}), watcher_status=lambda _: 422)
    status, reply, _ = harness.run(client_request())
    assert (status, reply) == (200, {"verdict": False}) and len(harness.watcher) == 1
