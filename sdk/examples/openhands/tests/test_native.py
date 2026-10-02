"""Real OpenHands Conversation dispatches callbacks with a deterministic fake LLM."""

import asyncio
import json

import httpx
from litellm.types.utils import ModelResponse
from openhands.sdk import Action, Agent, Observation, ToolDefinition
from openhands.sdk.conversation import LocalConversation
from openhands.sdk.llm import LLM, LLMResponse, Message, MessageToolCall, TextContent
from openhands.sdk.llm.utils.metrics import MetricsSnapshot, TokenUsage
from openhands.sdk.tool import Tool, ToolExecutor, register_tool
from watcher_openhands.integration import Recorder, convert, send

from watcher_sdk import AsyncWatcherClient


class FakeLLM(LLM):
    def completion(
        self, messages, tools=None, add_security_risk_prediction=False, on_token=None, call_context=None, **kwargs
    ):
        return LLMResponse(
            message=Message(role="assistant", content=[TextContent(text="native final answer")]),
            metrics=MetricsSnapshot(
                model_name="fixture",
                accumulated_cost=0,
                max_budget_per_task=0,
                accumulated_token_usage=TokenUsage(model="fixture"),
            ),
            raw_response=ModelResponse(id="fixture", choices=[]),
        )


def test_native_conversation_final_callback(tmp_path):
    recorder = Recorder()
    conversation = LocalConversation(
        agent=Agent(llm=FakeLLM(model="openai/gpt-4o", usage_id="fixture"), tools=[]),
        workspace=str(tmp_path),
        callbacks=[recorder],
        visualizer=None,
        profile_store_dir=tmp_path / "profiles",
    )
    conversation.send_message("Return a short answer")
    conversation.run()
    messages = convert(recorder.messages)
    assert any(row["role"] == "user" for row in messages)
    assert "native final answer" in str(messages[-1]["content"])
    requests = []

    def respond(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200, json=[])

    async def exercise():
        async with AsyncWatcherClient(
            httpx_client=httpx.AsyncClient(base_url="http://watcher.test", transport=httpx.MockTransport(respond))
        ) as client:
            await send(client, str(conversation.id), messages)

    asyncio.run(exercise())
    assert requests[-1]["messages"] == messages


class EchoAction(Action):
    text: str


class EchoObservation(Observation):
    output_text: str

    @property
    def to_llm_content(self):
        return [TextContent(text=self.output_text)]


EXECUTED = []


class EchoExecutor(ToolExecutor[EchoAction, EchoObservation]):
    def __call__(self, action, conversation=None):
        EXECUTED.append(action.text)
        return EchoObservation(output_text=action.text)


class EchoTool(ToolDefinition[EchoAction, EchoObservation]):
    @classmethod
    def create(cls, conv_state):
        return [
            cls(
                description="Echo fixture text without side effects",
                action_type=EchoAction,
                observation_type=EchoObservation,
                executor=EchoExecutor(),
            )
        ]


class ToolLLM(FakeLLM):
    def completion(
        self, messages, tools=None, add_security_risk_prediction=False, on_token=None, call_context=None, **kwargs
    ):
        response = super().completion(messages, tools, add_security_risk_prediction, on_token, call_context, **kwargs)
        if not any(message.role == "tool" for message in messages):
            response.message = Message(
                role="assistant",
                content=[],
                tool_calls=[
                    MessageToolCall(
                        id="native-echo",
                        name=EchoTool.name,
                        arguments='{"text":"native tool ran"}',
                        origin="completion",
                    )
                ],
            )
        return response


def test_native_tool_execution_identity_result_and_judgment(tmp_path):
    EXECUTED.clear()
    register_tool(EchoTool.name, EchoTool)
    recorder = Recorder()
    conversation = LocalConversation(
        agent=Agent(llm=ToolLLM(model="openai/gpt-4o", usage_id="fixture-tools"), tools=[Tool(name=EchoTool.name)]),
        workspace=str(tmp_path),
        callbacks=[recorder],
        visualizer=None,
        profile_store_dir=tmp_path / "profiles",
    )
    conversation.send_message("Echo the fixture text and finish")
    conversation.run()
    assert EXECUTED == ["native tool ran"]
    messages = convert(recorder.messages)
    assert [message["tool_call_id"] for message in messages if message["role"] == "tool"] == ["native-echo"]
    requests = []

    def respond(request):
        body = json.loads(request.content)
        requests.append(body)
        outcomes = [
            {
                "tool_use_id": item["tool_use_id"],
                "decision": "deferred",
                "judged_decision": "allow",
                "enforcement_mode": "observe",
                "decision_source": "rule",
                "latency_ms": 1,
                "verdict": {"summary": "fixture"},
            }
            for item in body["input"]
        ]
        return httpx.Response(200, json=outcomes)

    async def exercise():
        async with AsyncWatcherClient(
            httpx_client=httpx.AsyncClient(base_url="http://watcher.test", transport=httpx.MockTransport(respond))
        ) as client:
            await send(client, str(conversation.id), messages)

    asyncio.run(exercise())
    assert requests[0]["input"][0]["tool_use_id"] == "native-echo"
    assert requests[-1]["messages"] == messages
