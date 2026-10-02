"""Check identity, snapshot retention and deferred conversion at callback boundaries."""

from copy import deepcopy

import pytest
from crewai.agents.parser import AgentAction, AgentFinish
from crewai.llms.base_llm import BaseLLM
from watcher_crewai.adapter import ObservedLLM, WatcherTrace, messages_for_watcher


def completed_action(arguments='{"value": 2}'):
    return AgentAction(thought="Double two", tool="double", tool_input=arguments, text="Native action", result="4")


def test_repeated_callback_keeps_one_id_but_distinct_equal_actions_have_distinct_ids():
    trace = WatcherTrace("Double twice")
    first = completed_action()
    trace.on_step(first)
    snapshot = deepcopy(trace.messages)
    trace.on_step(first)
    assert trace.messages == snapshot
    trace.on_step(completed_action())
    calls = [call for message in messages_for_watcher(trace.messages) for call in message.get("tool_calls", [])]
    assert len(calls) == 2
    assert calls[0]["id"] == snapshot[1]["tool_calls"][0]["id"]
    assert calls[0]["id"] != calls[1]["id"]


@pytest.mark.parametrize("arguments", ["not-json", "[2]", "null", '"two"', "2"])
def test_malformed_arguments_fail_during_publication_after_callback_completes(arguments):
    trace = WatcherTrace("Double two")
    trace.on_step(completed_action(arguments))
    trace.finish("Native task completed")
    assert trace.messages[-1]["content"] == "Native task completed"
    with pytest.raises(ValueError):
        messages_for_watcher(trace.messages)


def test_unfinished_action_rejected_without_consuming_its_identity():
    trace = WatcherTrace("Double two")
    action = completed_action()
    action.result = None
    with pytest.raises(ValueError, match="completed action"):
        trace.on_step(action)
    action.result = "4"
    trace.on_step(action)
    assert len(messages_for_watcher(trace.messages)) == 3


def test_native_finish_is_not_duplicated_by_explicit_finish():
    trace = WatcherTrace("Double two")
    trace.on_step(AgentFinish(thought="Done", output="4", text="Final Answer: 4"))
    trace.finish("4")
    assert trace.messages == [{"role": "user", "content": "Double two"}, {"role": "assistant", "content": "4"}]


class CapturingLLM(BaseLLM):
    """Expose provider-facing stop words and arguments without calling a provider."""

    def __init__(self):
        super().__init__(model="fixture", temperature=0.25, stop=["initial"])
        self.calls = []
        self.capability_stops = []

    def call(self, messages, *args, **kwargs):
        self.calls.append({"messages": deepcopy(messages), "kwargs": kwargs, "stop": deepcopy(self.stop)})
        messages[0]["content"] = "Provider mutation"
        return "Final Answer: 4"

    def supports_stop_words(self):
        self.capability_stops.append(deepcopy(self.stop))
        return False

    def get_context_window_size(self):
        return 8192


def test_llm_wrapper_forwards_executor_stops_once_and_preserves_request_before_mutation():
    inner = CapturingLLM()
    trace = WatcherTrace("Initial")
    wrapper = ObservedLLM(inner, trace)
    wrapper.stop = ["Observation:"]
    messages = [{"role": "system", "content": "Actual system"}, {"role": "user", "content": "Actual request"}]
    before = deepcopy(messages)
    assert wrapper.supports_stop_words() is False
    assert wrapper.get_context_window_size() == 8192
    assert wrapper.call(messages, callbacks=["callback"]) == "Final Answer: 4"
    assert inner.capability_stops == [["Observation:"]]
    assert inner.calls == [{"messages": before, "kwargs": {"callbacks": ["callback"]}, "stop": ["Observation:"]}]
    assert trace.messages[1:-1] == before
    assert trace.messages[-1] == {"role": "assistant", "content": "Final Answer: 4"}
    assert inner.stop is not wrapper.stop


def test_string_model_request_is_retained_as_user_text():
    trace = WatcherTrace("Initial")
    trace.before_llm("Actual request")
    assert messages_for_watcher(trace.messages)[-1] == {"role": "user", "content": "Actual request"}
