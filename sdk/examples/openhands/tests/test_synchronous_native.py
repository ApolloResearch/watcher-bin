"""Exercise real OpenHands scheduling and a file-writing executor behind Watcher."""

import asyncio
import json
import threading
from pathlib import Path

import httpx
import pytest
from openhands.sdk import Action, Agent, Observation, ToolDefinition
from openhands.sdk.conversation import LocalConversation
from openhands.sdk.event import ActionEvent
from openhands.sdk.llm import Message, MessageToolCall, TextContent
from openhands.sdk.tool import Tool, ToolExecutor, register_tool
from test_native import FakeLLM
from watcher_openhands.integration import convert, send
from watcher_openhands.synchronous import EnforcementRecorder

from watcher_sdk import AsyncWatcherClient


class WriteAction(Action):
    path: str


class WriteObservation(Observation):
    @property
    def to_llm_content(self):
        return [TextContent(text="File written")]


class WriteExecutor(ToolExecutor[WriteAction, WriteObservation]):
    def __call__(self, action, conversation=None):
        Path(action.path).write_text("native side effect")
        return WriteObservation()


class WriteTool(ToolDefinition[WriteAction, WriteObservation]):
    @classmethod
    def create(cls, conv_state):
        return [
            cls(
                description="Write a fixture marker",
                action_type=WriteAction,
                observation_type=WriteObservation,
                executor=WriteExecutor(),
            )
        ]


class NativeLLM(FakeLLM):
    target: str = ""

    def completion(
        self, messages, tools=None, add_security_risk_prediction=False, on_token=None, call_context=None, **kwargs
    ):
        response = super().completion(messages, tools, add_security_risk_prediction, on_token, call_context, **kwargs)
        if not any(m.role == "tool" for m in messages):
            response.message = Message(
                role="assistant",
                content=[],
                tool_calls=[
                    MessageToolCall(
                        id="native-write",
                        name=WriteTool.name,
                        arguments=json.dumps({"path": self.target}),
                        origin="completion",
                    )
                ],
            )
        return response


@pytest.mark.parametrize(
    "decision",
    [
        "allow",
        "deny",
        "escalate",
        "deferred",
        "identity-error",
        "missing-outcome",
        "http-error",
        "pending",
        "replacement-block",
    ],
)
def test_native_execution_waits_for_recorded_allow(tmp_path, decision):
    marker = tmp_path / "marker"
    requests = []
    entered, release = threading.Event(), threading.Event()

    def respond(request):
        body = json.loads(request.content)
        requests.append(body)
        enforcing = bool(body["input"]) and "settings_overrides" not in body
        if enforcing and decision in {"pending", "replacement-block"}:
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

    register_tool(WriteTool.name, WriteTool)
    recorder = EnforcementRecorder(client)
    action_ids = []

    def capture_action(event):
        if isinstance(event, ActionEvent):
            action_ids.append(event.id)

    conversation = LocalConversation(
        agent=Agent(
            llm=NativeLLM(model="openai/gpt-4o", usage_id="fixture", target=str(marker)),
            tools=[Tool(name=WriteTool.name)],
        ),
        workspace=str(tmp_path),
        callbacks=[capture_action, recorder],
        visualizer=None,
        profile_store_dir=tmp_path / "profiles",
    )
    recorder.bind(conversation)
    conversation.send_message("Write a fixture marker and finish")
    if decision in {"pending", "replacement-block"}:
        worker = threading.Thread(target=conversation.run)
        worker.start()
        assert entered.wait(10)
        assert not marker.exists()
        if decision == "replacement-block":
            (action_id,) = action_ids
            conversation.state.block_action(action_id, "Local policy denied the tool")
        release.set()
        worker.join(10)
        assert not worker.is_alive()
    else:
        conversation.run()
    assert marker.exists() == (decision == "allow")
    messages = convert(recorder.messages)
    assert any(m.get("tool_call_id") == "native-write" for m in messages)
    assert "native final answer" in str(messages[-1]["content"])
    if decision == "replacement-block":
        assert "Local policy denied the tool" in json.dumps(messages)
    assert requests[0]["input"][0]["tool_use_id"] == "native-write"
    assert not any(m.get("tool_call_id") == "native-write" for m in requests[0]["messages"])

    async def observe():
        async with client() as watcher:
            await send(watcher, str(conversation.id), messages, record_only=True)

    asyncio.run(observe())
    assert requests[-1]["messages"] == messages
