"""Incremental delivery through the installed LiteLLM HTTP server, in all formats.

The provider and Watcher peers are deterministic local HTTP fixtures. Explicit
gates establish ordering: early text must arrive while the provider is paused,
and only keepalives may arrive while a Watcher decision is pending. Native SDK
parsers separately verify that allowed streams remain valid client protocols.
"""

import json
import os
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from queue import Queue
from typing import Any

import anthropic
import httpx
import openai
import pytest
from harness import litellm_proxy, serve_in_thread
from incremental_servers import API, Scenario, ScenarioHolder, provider_app, watcher_app
from pydantic import BaseModel, ConfigDict, Field

APIS: list[API] = ["messages", "chat_completions", "responses"]
_USE_DEFAULT_TIMEOUT = os.environ.get("WATCHER_LITELLM_TEST_DEFAULT_TIMEOUT") == "1"


class Frame(BaseModel):
    """One raw SSE frame and the client-side monotonic receipt time."""

    wire: str
    received: float = Field(default_factory=time.monotonic)

    @property
    def data(self) -> dict[str, Any]:
        value = "\n".join(line[5:].lstrip() for line in self.wire.splitlines() if line.startswith("data:"))
        return json.loads(value) if value and value != "[DONE]" else {}

    @property
    def is_keepalive(self) -> bool:
        return self.wire.startswith(":") or self.data.get("type") == "ping"

    @property
    def has_tool(self) -> bool:
        body = self.data
        delta = body.get("delta")
        message = body.get("message")
        return (
            body.get("content_block", {}).get("type") == "tool_use"
            or body.get("item", {}).get("type") == "function_call"
            or (isinstance(delta, dict) and delta.get("type") == "input_json_delta")
            or body.get("type", "").startswith("response.function_call_arguments.")
            or any(
                choice.get("delta", {}).get("tool_calls") or choice.get("delta", {}).get("function_call")
                for choice in body.get("choices", [])
            )
            or any(item.get("type") == "function_call" for item in body.get("response", {}).get("output", []))
            or (
                isinstance(message, dict)
                and any(block.get("type") == "tool_use" for block in message.get("content", []))
            )
        )


class Reader(BaseModel):
    """Read a streaming HTTP response in a thread while tests control its peers."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    queue: Queue[Frame | Exception | None] = Field(default_factory=Queue)
    frames: list[Frame] = Field(default_factory=list)
    cancel: threading.Event = Field(default_factory=threading.Event)
    stopped: threading.Event = Field(default_factory=threading.Event)
    started: float = Field(default_factory=time.monotonic)

    def receive(self) -> Frame:
        """Consume one frame, exposing HTTP and producer failures to pytest."""
        item = self.queue.get(timeout=15)
        if isinstance(item, Exception):
            raise item
        assert item is not None, "stream ended before the expected frame"
        self.frames.append(item)
        return item

    def through(self, predicate: Callable[[Frame], bool], *, timeout: float = 15) -> Frame:
        """Consume until the expected frame arrives, with a finite global bound."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            frame = self.receive()
            if predicate(frame):
                return frame
        raise AssertionError("expected SSE frame did not arrive")

    def finish(self) -> None:
        """Drain a complete stream and preserve all frames for protocol assertions."""
        while True:
            item = self.queue.get(timeout=10)
            if item is None:
                return
            if isinstance(item, Exception):
                raise item
            self.frames.append(item)


@pytest.fixture(scope="module")
def incremental_holder() -> ScenarioHolder:
    return ScenarioHolder()


@pytest.fixture
def scenario(incremental_holder: ScenarioHolder) -> Iterator[Scenario]:
    state = Scenario()
    incremental_holder.current = state
    incremental_holder.cases[state.case_id] = state
    yield state
    state.start_tools.set()
    state.finish_provider.set()
    for grade in tuple(state.grades.queue):
        grade.release.set()


@pytest.fixture(scope="module")
def incremental_proxy(incremental_holder: ScenarioHolder, tmp_path_factory: pytest.TempPathFactory) -> Iterator[str]:
    provider = serve_in_thread(provider_app(incremental_holder))
    watcher = serve_in_thread(watcher_app(incremental_holder))
    workdir = tmp_path_factory.mktemp("incremental-proxy")
    settings = "" if _USE_DEFAULT_TIMEOUT else "timeout_seconds=2, ping_seconds=0.1"
    (workdir / "incremental_callback.py").write_text(
        f"from watcher_litellm.callback import WatcherCallback\ncallback = WatcherCallback({settings})\n"
    )
    models = [
        {
            "model_name": "gpt-test",
            "litellm_params": {"model": "openai/gpt-test", "api_base": f"{provider}/v1", "api_key": "k"},
        },
        {
            "model_name": "claude-test",
            "litellm_params": {"model": "anthropic/claude-test", "api_base": provider, "api_key": "k"},
        },
    ]
    env = {"WATCHER_API_URL": watcher, "WATCHER_API_KEY": "fixture", "PYTHONPATH": str(workdir)}
    with litellm_proxy(models, env, workdir, callback="incremental_callback.callback") as url:
        yield url


@contextmanager
def read_stream(proxy: str, api: API, case_id: str) -> Iterator[Reader]:
    """Open the public HTTP streaming API with no client retry or buffering layer."""
    reader = Reader()

    def read() -> None:
        body: dict[str, Any] = {"model": "claude-test" if api == "messages" else "gpt-test", "stream": True}
        if api == "responses":
            body["input"] = "Read two files."
        else:
            body["messages"] = [{"role": "user", "content": "Read two files."}]
        if api == "messages":
            body["max_tokens"] = 100
        path = "chat/completions" if api == "chat_completions" else api
        try:
            with httpx.stream(
                "POST", f"{proxy}/v1/{path}", json=body, headers={"x-watcher-session-id": case_id}, timeout=15
            ) as response:
                response.raise_for_status()
                lines: list[str] = []
                for line in response.iter_lines():
                    if reader.cancel.is_set():
                        break
                    if line:
                        lines.append(line)
                    elif lines:
                        reader.queue.put(Frame(wire="\n".join(lines)))
                        lines = []
        except Exception as exc:
            reader.queue.put(exc)
        finally:
            reader.stopped.set()
            reader.queue.put(None)

    thread = threading.Thread(target=read, daemon=True)
    thread.start()
    try:
        yield reader
    finally:
        reader.cancel.set()
        thread.join(timeout=5)


def is_error(frame: Frame) -> bool:
    """Recognize an API's explicit terminal streaming error, independently of its message."""
    return "error" in frame.data or frame.data.get("type") in {"error", "response.failed"}


def test_messages_sdk_accepts_keepalives_before_the_first_provider_event(
    incremental_proxy: str, scenario: Scenario
) -> None:
    scenario.text_only = True
    scenario.initial_stream_delay_seconds = 0.3
    with read_stream(incremental_proxy, "messages", scenario.case_id) as reader:
        first = reader.receive()
        assert first.is_keepalive
        assert first.wire.startswith(":")
        reader.finish()
        assert reader.frames[-1].data["type"] == "message_stop"
    with (
        anthropic.Anthropic(
            base_url=incremental_proxy,
            api_key="fixture",
            max_retries=0,
            default_headers={"x-watcher-session-id": scenario.case_id},
        ) as client,
        client.messages.stream(
            model="claude-test", max_tokens=100, messages=[{"role": "user", "content": "Read a file."}]
        ) as events,
    ):
        message = events.get_final_message()
    assert [block.text for block in message.content if block.type == "text"] == ["before"]


def test_chat_text_and_two_calls_in_one_chunk_are_released_independently(
    incremental_proxy: str, scenario: Scenario
) -> None:
    scenario.combined_chat_chunks = True
    with read_stream(incremental_proxy, "chat_completions", scenario.case_id) as reader:
        reader.through(lambda frame: "before" in frame.wire)
        assert scenario.requests == []
        assert not any(frame.has_tool for frame in reader.frames)
        scenario.finish_provider.set()
        first = scenario.grades.get(timeout=10)
        assert first.ids == ["call_0"]
        reader.through(lambda frame: frame.is_keepalive)
        assert not any(frame.has_tool for frame in reader.frames)
        first.release.set()
        reader.through(lambda frame: frame.has_tool)
        second = scenario.grades.get(timeout=10)
        assert second.ids == ["call_1"]
        reader.through(lambda frame: frame.is_keepalive)
        calls = [
            call
            for frame in reader.frames
            for choice in frame.data.get("choices", [])
            for call in choice["delta"].get("tool_calls") or []
        ]
        assert [call["id"] for call in calls] == ["call_0"]
        second.release.set()
        reader.finish()
        assert not any(is_error(frame) for frame in reader.frames)
        calls = [
            call
            for frame in reader.frames
            for choice in frame.data.get("choices", [])
            for call in choice["delta"].get("tool_calls") or []
        ]
        assert [call["index"] for call in calls] == [0, 1, 1, 0]
        assert [call["function"]["arguments"] for call in calls] == ['{"path":', '{"path":', '"f1"}', '"f0"}']
        assert (
            sum(
                choice["finish_reason"] is not None
                for frame in reader.frames
                for choice in frame.data.get("choices", [])
            )
            == 1
        )
        assert sum(bool(frame.data.get("usage")) for frame in reader.frames) == 1


@pytest.mark.parametrize("api", APIS)
def test_text_only_stream_closes_before_a_stalled_recording_finishes(
    incremental_proxy: str, scenario: Scenario, api: API
) -> None:
    scenario.text_only = True
    scenario.hold_recording = True
    with read_stream(incremental_proxy, api, scenario.case_id) as reader:
        reader.finish()
        delivered = time.monotonic() - reader.started
        assert delivered < 1
        assert any("before" in frame.wire for frame in reader.frames)
        assert not any(frame.has_tool or is_error(frame) for frame in reader.frames)
        if api == "messages":
            assert reader.frames[-1].data["type"] == "message_stop"
        else:
            assert reader.frames[-1].wire == "data: [DONE]"
        recording = scenario.grades.get(timeout=10)
        assert recording.ids == []
        assert not recording.release.is_set()
        assert recording.disconnected.wait(5)
        assert time.monotonic() - recording.started >= 1.5


@pytest.mark.parametrize("api", APIS)
def test_text_and_each_allowed_call_arrive_before_the_next_grade(
    incremental_proxy: str,
    scenario: Scenario,
    api: API,
    record_property: Callable[[str, object], None],
) -> None:
    with read_stream(incremental_proxy, api, scenario.case_id) as reader:
        early = reader.through(lambda frame: "before" in frame.wire)
        assert scenario.requests == []
        assert not scenario.provider_finished.is_set()
        scenario.start_tools.set()
        if api == "chat_completions":
            # Chat has no per-call completion marker; the interleaved calls are
            # complete only when the provider finishes the choice.
            scenario.finish_provider.set()
        first = scenario.grades.get(timeout=10)
        assert first.ids == ["call_0"]
        keepalive = reader.through(lambda frame: frame.is_keepalive)
        assert not any(frame.has_tool for frame in reader.frames)
        assert not any("between" in frame.wire for frame in reader.frames)
        first_release = time.monotonic()
        first.release.set()
        first_tool = reader.through(lambda frame: frame.has_tool)
        between = reader.through(lambda frame: "between" in frame.wire)
        assert first_tool.received >= first_release
        assert between.received - first_release < 1
        scenario.finish_provider.set()
        second = scenario.grades.get(timeout=10)
        assert second.ids == ["call_1"]
        reader.through(lambda frame: frame.is_keepalive)
        assert not any('"call_1"' in frame.wire and frame.has_tool for frame in reader.frames)
        assert not any("after" in frame.wire for frame in reader.frames)
        second_release = time.monotonic()
        second.release.set()
        reader.through(lambda frame: "after" in frame.wire)
        reader.finish()
        record_property(
            "timing_seconds",
            json.dumps(
                {
                    "early_text": early.received - reader.started,
                    "first_grade_started": first.started - reader.started,
                    "keepalive_during_grade": keepalive.received - first.started,
                    "first_release_to_tool": first_tool.received - first_release,
                    "first_release_to_following_text": between.received - first_release,
                    "second_grade_started": second.started - reader.started,
                    "second_release": second_release - reader.started,
                }
            ),
        )
        record_property("wire", "\n\n".join(frame.wire for frame in reader.frames))
        assert [frame.wire for frame in reader.frames if is_error(frame)] == []


@pytest.mark.parametrize("api", APIS)
@pytest.mark.parametrize("failure", ["deny", "timeout", "watcher_error"])
def test_grading_failure_terminates_without_exposing_a_tool(
    incremental_proxy: str,
    scenario: Scenario,
    api: API,
    failure: str,
    record_property: Callable[[str, object], None],
) -> None:
    with read_stream(incremental_proxy, api, scenario.case_id) as reader:
        reader.through(lambda frame: "before" in frame.wire)
        scenario.start_tools.set()
        scenario.finish_provider.set()
        grade = scenario.grades.get(timeout=10)
        reader.through(lambda frame: frame.is_keepalive)
        if failure != "timeout":
            grade.decision = "deny" if failure == "deny" else "allow"
            grade.status_code = 503 if failure == "watcher_error" else 200
            grade.release.set()
        if failure == "deny":
            reader.finish()
            assert [frame.wire for frame in reader.frames if frame.has_tool or is_error(frame)] == []
            assert any("Fixture denied this call." in frame.wire for frame in reader.frames)
            return
        error = reader.through(is_error, timeout=310 if _USE_DEFAULT_TIMEOUT else 15)
        reader.finish()
        assert not any(frame.has_tool for frame in reader.frames)
        assert not any("between" in frame.wire or "after" in frame.wire for frame in reader.frames)
        assert "Watcher" in error.wire
        if failure == "timeout":
            expected = 300 if _USE_DEFAULT_TIMEOUT else 2
            elapsed = error.received - grade.started
            assert expected - 0.5 < elapsed < expected + 2
            assert "timed out" in error.wire
            keepalives = [frame for frame in reader.frames if frame.is_keepalive]
            assert len(keepalives) >= (25 if _USE_DEFAULT_TIMEOUT else 2)
            record_property("timeout_seconds", elapsed)
            record_property("keepalive_count", len(keepalives))
            record_property("keepalive_times", [frame.received - grade.started for frame in keepalives])
            record_property("wire", "\n\n".join(frame.wire for frame in reader.frames))


@pytest.mark.parametrize("api", APIS)
def test_disconnect_closes_the_pending_watcher_request(incremental_proxy: str, scenario: Scenario, api: API) -> None:
    with read_stream(incremental_proxy, api, scenario.case_id) as reader:
        reader.through(lambda frame: "before" in frame.wire)
        scenario.start_tools.set()
        scenario.finish_provider.set()
        grade = scenario.grades.get(timeout=10)
        reader.through(lambda frame: frame.is_keepalive)
        reader.cancel.set()
        assert reader.stopped.wait(5)
        assert grade.disconnected.wait(5)
        assert not any(frame.has_tool for frame in reader.frames)


@pytest.mark.parametrize("api", APIS)
def test_later_denial_preserves_only_the_previously_allowed_call(
    incremental_proxy: str, scenario: Scenario, api: API
) -> None:
    with read_stream(incremental_proxy, api, scenario.case_id) as reader:
        reader.through(lambda frame: "before" in frame.wire)
        scenario.start_tools.set()
        scenario.finish_provider.set()
        first = scenario.grades.get(timeout=10)
        assert first.ids == ["call_0"]
        first.release.set()
        reader.through(lambda frame: frame.has_tool)
        reader.through(lambda frame: "between" in frame.wire)
        second = scenario.grades.get(timeout=10)
        assert second.ids == ["call_1"]
        second.decision = "deny"
        second.release.set()
        reader.finish()
        assert not any(is_error(frame) for frame in reader.frames)
        assert any('"call_0"' in frame.wire and frame.has_tool for frame in reader.frames)
        assert not any('"call_1"' in frame.wire and frame.has_tool for frame in reader.frames)
        assert not any("after" in frame.wire for frame in reader.frames)


@pytest.mark.parametrize("api", APIS)
def test_provider_wait_does_not_consume_the_grading_timeout(
    incremental_proxy: str, scenario: Scenario, api: API
) -> None:
    scenario.auto_allow = True
    scenario.finish_provider.set()
    with read_stream(incremental_proxy, api, scenario.case_id) as reader:
        reader.through(lambda frame: "before" in frame.wire)
        # The gate deliberately stays closed longer than the configured 2s
        # grading deadline; no Watcher request exists during that interval.
        timer = threading.Timer(2.2, scenario.start_tools.set)
        timer.start()
        try:
            reader.finish()
        finally:
            timer.cancel()
        assert not any(is_error(frame) for frame in reader.frames)
        assert any('"call_0"' in frame.wire and frame.has_tool for frame in reader.frames)
        assert any('"call_1"' in frame.wire and frame.has_tool for frame in reader.frames)


@pytest.mark.parametrize("api", APIS)
def test_provider_error_after_early_text_never_delivers_calls(
    incremental_proxy: str, scenario: Scenario, api: API
) -> None:
    scenario.provider_error = True
    with read_stream(incremental_proxy, api, scenario.case_id) as reader:
        reader.through(lambda frame: "before" in frame.wire)
        scenario.start_tools.set()
        reader.through(is_error)
        reader.finish()
        assert scenario.requests == []
        assert not any(frame.has_tool for frame in reader.frames)


@pytest.mark.parametrize("api", APIS)
def test_native_sdk_assembles_two_allowed_calls_in_order(incremental_proxy: str, scenario: Scenario, api: API) -> None:
    scenario.start_tools.set()
    scenario.finish_provider.set()
    scenario.auto_allow = True
    scenario.auto_allow_delay = 0.15
    if api == "messages":
        with (
            anthropic.Anthropic(
                base_url=incremental_proxy,
                api_key="fixture",
                max_retries=0,
                default_headers={"x-watcher-session-id": scenario.case_id},
            ) as client,
            client.messages.stream(
                model="claude-test", max_tokens=100, messages=[{"role": "user", "content": "Read two files."}]
            ) as stream,
        ):
            message = stream.get_final_message()
        assert [block.id for block in message.content if block.type == "tool_use"] == ["call_0", "call_1"]
        assert [block.input for block in message.content if block.type == "tool_use"] == [
            {"path": "f0"},
            {"path": "f1"},
        ]
        assert [block.text for block in message.content if block.type == "text"] == ["before", "between", "after"]
    else:
        with openai.OpenAI(
            base_url=f"{incremental_proxy}/v1",
            api_key="fixture",
            max_retries=0,
            default_headers={"x-watcher-session-id": scenario.case_id},
        ) as client:
            if api == "responses":
                with client.responses.stream(model="gpt-test", input="Read two files.") as stream:
                    response = stream.get_final_response()
                calls = [item for item in response.output if item.type == "function_call"]
                assert [call.call_id for call in calls] == ["call_0", "call_1"]
                assert [json.loads(call.arguments) for call in calls] == [{"path": "f0"}, {"path": "f1"}]
                assert response.output_text == "beforebetweenafter"
            else:
                with client.chat.completions.stream(
                    model="gpt-test", messages=[{"role": "user", "content": "Read two files."}]
                ) as stream:
                    completion = stream.get_final_completion()
                calls = completion.choices[0].message.tool_calls
                assert calls is not None
                assert [call.id for call in calls] == ["call_0", "call_1"]
                assert [json.loads(call.function.arguments) for call in calls] == [{"path": "f0"}, {"path": "f1"}]
                assert completion.choices[0].message.content == "beforebetweenafter"
