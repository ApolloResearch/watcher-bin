"""Resolved ADK instructions reach Watcher before execution and in final history."""

import json
from contextlib import asynccontextmanager

import httpx
import pytest
from demo import enforce
from google.adk.agents import LlmAgent
from watcher_google_adk.adapter import messages_for_watcher
from watcher_google_adk.monitoring import Monitor
from watcher_google_adk.native import ConversationHistory

from watcher_sdk import AsyncWatcherClient


def dynamic_instruction(context):
    """Resolve text through ADK's native instruction-provider interface."""
    return f"Only use the double tool in agent {context.agent_name}."


def changing_instruction(context):
    """Change instructions after actual native tools have returned results."""
    if any(
        part.function_response
        for event in context.session.events
        if event.content is not None
        for part in event.content.parts or []
    ):
        return "Summarize the results without calling more tools."
    return "Only use the double tool in agent example."


@asynccontextmanager
async def client_for(respond):
    async with (
        httpx.AsyncClient(base_url="https://watcher.invalid", transport=httpx.MockTransport(respond)) as transport,
        AsyncWatcherClient(
            "https://watcher.invalid",
            httpx_client=transport,
            manage_external_httpx_client_lifecycle=False,
            max_retries=0,
        ) as client,
    ):
        yield client


def allow_response(body):
    if body["input"] is None:
        return httpx.Response(200, json=[])
    return httpx.Response(
        200,
        json={
            "decision": "allow",
            "judged_decision": "allow",
            "enforcement_mode": "enforce",
            "decision_source": "rule",
            "tool_use_id": body["input"]["tool_use_id"],
            "latency_ms": 1,
            "verdict": {"severity_score": None, "severity_label": None, "summary": "Fixture", "explanation": "Fixture"},
        },
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "instruction, final_instruction, expected_roles",
    [
        (
            "Only use the double tool in agent example.",
            'Only use the double tool in agent example.\n\nYou are an agent. Your internal name is "example".',
            ["system", "user", "assistant", "tool", "tool", "assistant"],
        ),
        (
            dynamic_instruction,
            'Only use the double tool in agent example.\n\nYou are an agent. Your internal name is "example".',
            ["system", "user", "assistant", "tool", "tool", "assistant"],
        ),
        (
            changing_instruction,
            'Summarize the results without calling more tools.\n\nYou are an agent. Your internal name is "example".',
            ["system", "user", "assistant", "tool", "tool", "system", "assistant"],
        ),
    ],
)
async def test_resolved_instruction_is_sent_before_tools_and_retained_in_final_record(
    instruction, final_instruction, expected_roles, monkeypatch, record_property
):
    sent, effects, model_instructions = [], [], []

    class CapturingModel(enforce.DeterministicModel):
        """Retain the request received by the installed ADK model interface."""

        async def generate_content_async(self, llm_request, stream=False):
            model_instructions.append(llm_request.config.system_instruction)
            async for response in super().generate_content_async(llm_request, stream):
                yield response

    class CheckedHistory(ConversationHistory):
        """Check capture against real ADK requests and sessions, without replacing them."""

        def before_model_callback(self, callback_context, llm_request):
            request_before = llm_request.model_dump(exclude={"tools_dict"})
            session_before = callback_context.session.model_dump()
            result = super().before_model_callback(callback_context, llm_request)
            assert result is None
            assert llm_request.model_dump(exclude={"tools_dict"}) == request_before
            assert callback_context.session.model_dump() == session_before
            retained_before = [message.model_dump() for message in self.messages(callback_context.session)]
            copy = self.messages(callback_context.session)
            assert copy[0].parts
            copy[0].parts[0].text = "Changed by a consumer"
            assert [message.model_dump() for message in self.messages(callback_context.session)] == retained_before
            assert callback_context.session.model_dump() == session_before

    def configured_agent(**kwargs):
        return LlmAgent(instruction=instruction, **kwargs)

    monkeypatch.setattr(enforce, "ConversationHistory", CheckedHistory)
    monkeypatch.setattr(enforce, "LlmAgent", configured_agent)
    monkeypatch.setattr(enforce, "DeterministicModel", CapturingModel)

    def effect(value):
        assert sent and sent[-1]["input"] is not None
        effects.append(value)
        return str(value * 2)

    async def respond(request):
        body = json.loads(request.content)
        sent.append(body)
        assert body["messages"][0] == {
            "role": "system",
            "content": 'Only use the double tool in agent example.\n\nYou are an agent. Your internal name is "example".',
        }
        if body["input"] is None:
            return httpx.Response(200, json=[])
        assert body["messages"][0]["content"] == model_instructions[0]
        call = body["input"]
        assert call["tool_input"]["value"] not in effects
        return allow_response(body)

    async with client_for(respond) as client:
        history = await enforce.run_conversation(Monitor(client, "instruction"), effect)
    record_property("model_system_instructions", json.dumps(model_instructions))
    record_property("watcher_requests", json.dumps(sent))
    record_property("native_effects", json.dumps(effects))
    assert sorted(effects) == [2, 3]
    assert sent[-1]["input"] is None
    assert sent[-1]["messages"] == messages_for_watcher(history)
    assert sent[-1]["messages"][-1] == {"role": "assistant", "content": "4 and 6"}
    assert model_instructions == [
        'Only use the double tool in agent example.\n\nYou are an agent. Your internal name is "example".',
        final_instruction,
    ]
    assert [message["role"] for message in sent[-1]["messages"]] == expected_roles
    assert [message["content"] for message in sent[-1]["messages"] if message["role"] == "system"][
        -1
    ] == final_instruction
    for request in sent[:-1]:
        assert request["messages"] == sent[-1]["messages"][: len(request["messages"])]


@pytest.mark.asyncio
async def test_missing_before_model_capture_blocks_native_tool_before_watcher(monkeypatch):
    effects = []

    def missing_capture_agent(**kwargs):
        kwargs.pop("before_model_callback")
        return LlmAgent(**kwargs)

    async def respond(request):
        pytest.fail("A missing model capture must fail before submitting a Watcher request")

    monkeypatch.setattr(enforce, "LlmAgent", missing_capture_agent)
    async with client_for(respond) as client:
        with pytest.raises(Exception, match="Register ConversationHistory.before_model_callback"):
            await enforce.run_conversation(Monitor(client, "missing-capture"), effects.append)
    assert effects == []


@pytest.mark.asyncio
async def test_history_reuse_in_another_native_session_is_rejected_before_tools(monkeypatch):
    history = ConversationHistory()
    effects, sent = [], []
    monkeypatch.setattr(enforce, "ConversationHistory", lambda: history)

    async def respond(request):
        body = json.loads(request.content)
        sent.append(body)
        return allow_response(body)

    def effect(value):
        effects.append(value)
        return str(value * 2)

    async with client_for(respond) as client:
        await enforce.run_conversation(Monitor(client, "first-session"), effect)
        assert sorted(effects) == [2, 3]
        request_count = len(sent)
        with pytest.raises(Exception, match="Create one ConversationHistory per ADK session"):
            await enforce.run_conversation(Monitor(client, "another-session"), effect)
    assert len(sent) == request_count
    assert sorted(effects) == [2, 3]
