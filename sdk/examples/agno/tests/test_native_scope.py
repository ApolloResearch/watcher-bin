"""Installed Agno tool generation and application pre-hook control flow stay explicit."""

import pytest
from agno.agent import Agent
from agno.exceptions import AgentRunException, RetryAgentRun, StopAgentRun
from agno.models.response import ModelResponse
from agno.run.agent import RunOutput
from agno.session.agent import AgentSession
from agno.tools.function import Function
from demo.enforce import MonitoredModel
from watcher_agno import WatcherAgent


class RecordingMonitor:
    """Observe permission checks without a Watcher server or model credentials."""

    def __init__(self):
        self.calls = []

    async def before(self, history, call_id, name, arguments):
        self.calls.append((call_id, name, arguments))


def knowledge_retriever(*args, **kwargs):
    """A generation test must never query an external knowledge source."""
    raise AssertionError("The knowledge retriever must not execute")


@pytest.mark.parametrize(
    "options,generated_name,rejected_option",
    [
        ({"read_chat_history": True}, "get_chat_history", "read_chat_history"),
        ({"read_tool_call_history": True}, "get_tool_call_history", "read_tool_call_history"),
        ({"search_session_history": True}, "get_previous_session_messages", "search_session_history"),
        ({"enable_agentic_memory": True}, "update_user_memory", "enable_agentic_memory"),
        ({"enable_agentic_culture": True}, "create_or_update_cultural_knowledge", "enable_agentic_culture"),
        ({"enable_agentic_state": True}, "update_session_state", "enable_agentic_state"),
        ({"knowledge": object()}, "search_knowledge_base", "search_knowledge"),
        ({"knowledge_retriever": knowledge_retriever}, "search_knowledge_base", "search_knowledge"),
        (
            {"knowledge": object(), "enable_agentic_knowledge_filters": True},
            "search_knowledge_base_with_agentic_filters",
            "search_knowledge",
        ),
        (
            {"knowledge": object(), "search_knowledge": False, "update_knowledge": True},
            "add_to_knowledge",
            "update_knowledge",
        ),
        (
            {"knowledge_retriever": knowledge_retriever, "search_knowledge": False, "update_knowledge": True},
            "add_to_knowledge",
            "update_knowledge",
        ),
    ],
)
def test_agno_generated_tools_are_refused_before_dispatch(options, generated_name, rejected_option):
    """The native package really adds each rejected tool, rather than a guessed feature flag."""
    model_calls, effects = [], []

    class CountedModel(MonitoredModel):
        def invoke(self, messages, **kwargs):
            model_calls.append(messages)
            return super().invoke(messages, **kwargs)

    def effect() -> str:
        effects.append("ran")
        return "ran"

    plain = Agent(model=CountedModel(id="local"), tools=[], telemetry=False, **options)
    generated = plain.get_tools(run_response=RunOutput(), session=AgentSession(session_id="fixture"))
    assert [tool.name if isinstance(tool, Function) else tool.__name__ for tool in generated] == [generated_name]

    monitor = RecordingMonitor()
    with pytest.raises(TypeError, match=rejected_option):
        WatcherAgent(
            monitor,
            model=CountedModel(id="local"),
            tools=[Function.from_callable(effect)],
            telemetry=False,
            **options,
        )
    assert model_calls == [] and monitor.calls == [] and effects == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "options",
    [
        {"search_knowledge": True, "enable_agentic_knowledge_filters": True},
        {"knowledge": object(), "search_knowledge": False, "update_knowledge": False},
        {"knowledge_retriever": knowledge_retriever, "search_knowledge": False, "update_knowledge": False},
    ],
)
async def test_options_that_add_no_native_tools_keep_the_registered_list(options):
    effects = []

    def effect() -> str:
        effects.append("ran")
        return "ran"

    agent = WatcherAgent(
        RecordingMonitor(),
        model=MonitoredModel(id="local"),
        tools=[Function.from_callable(effect)],
        telemetry=False,
        **options,
    )
    actual = await agent.aget_tools(run_response=RunOutput(), session=AgentSession(session_id="fixture"))
    assert [tool.name for tool in actual] == ["effect"]
    assert all(tool.pre_hook is not None for tool in actual)
    assert effects == []


@pytest.mark.asyncio
@pytest.mark.parametrize("asynchronous", [False, True])
@pytest.mark.parametrize("exception_type", [RetryAgentRun, StopAgentRun])
async def test_application_retry_and_stop_reach_agno_with_messages_and_no_initial_effect(asynchronous, exception_type):
    """Native retries get another model turn; stops retain messages and never execute a tool."""
    effects, native_exceptions, provider_calls = [], [], []
    monitor = RecordingMonitor()
    application_error = exception_type(
        "application refusal",
        user_message="Application user guidance",
        agent_message="Application agent guidance",
        messages=[{"role": "user", "content": "Application extra context"}],
    )

    def double(value: int) -> str:
        effects.append(value)
        return str(value * 2)

    def permission(fc):
        if fc.call_id == "first-attempt":
            raise application_error

    async def async_permission(fc):
        permission(fc)

    class ObservedModel(MonitoredModel):
        def invoke(self, messages, **kwargs):
            provider_calls.append(list(messages))
            if len(provider_calls) == 2:
                assert exception_type is RetryAgentRun
                assert effects == [] and monitor.calls == []
                assert any(
                    message.role == "user" and message.content == "Application user guidance" for message in messages
                )
                assert any(
                    message.role == "assistant" and message.content == "Application agent guidance"
                    for message in messages
                )
                assert any(message.content == "Application extra context" for message in messages)
            if len(provider_calls) > 2:
                return ModelResponse(role="assistant", content="Retried safely")
            return ModelResponse(
                role="assistant",
                tool_calls=[
                    {
                        "id": "first-attempt" if len(provider_calls) == 1 else "second-attempt",
                        "type": "function",
                        "function": {"name": "double", "arguments": '{"value":2}'},
                    }
                ],
            )

        async def arun_function_call(self, function_call):
            result = await super().arun_function_call(function_call)
            if isinstance(result[0], AgentRunException):
                native_exceptions.append(result[0])
            return result

    function = Function.from_callable(double)
    function.pre_hook = async_permission if asynchronous else permission
    agent = WatcherAgent(monitor, model=ObservedModel(id="local"), tools=[function], telemetry=False)
    result = await agent.arun("Double one number")

    assert native_exceptions == [application_error]
    assert native_exceptions[0] is application_error
    assert str(application_error) == "application refusal"
    assert application_error.user_message == "Application user guidance"
    assert application_error.agent_message == "Application agent guidance"
    assert application_error.messages == [{"role": "user", "content": "Application extra context"}]
    assert any(message.content == "Application user guidance" for message in result.messages)
    assert any(message.content == "Application agent guidance" for message in result.messages)
    if exception_type is RetryAgentRun:
        assert effects == [2]
        assert monitor.calls == [("second-attempt", "double", {"value": 2})]
        assert len(provider_calls) == 3
    else:
        assert effects == [] and monitor.calls == []
        assert len(provider_calls) == 1
