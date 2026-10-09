"""Live checks through real providers and a real Watcher server.

Each provider route behind the proxy is called through all three client APIs,
buffered and streamed. The model is forced to call one tool: a denied one,
which must be withheld with an explanation, or an allowed one, which must be
released and then answered with a tool result in a second request. Watcher's
own records are then read back through the SDK. ``WATCHER_LIVE_ROUTES``
selects a comma-separated subset of ``ROUTES``; see the README for setup.
"""

import json
import os
import uuid
from collections.abc import Iterator
from typing import Any, cast

import anthropic
import openai
import pytest
from common import GATEWAY, GATEWAY_KEY, GOOGLE_PROJECT, WATCHER_URL, recorded_calls
from harness import litellm_proxy
from openai.types.chat.completion_create_params import CompletionCreateParamsBase
from openai.types.responses import FunctionToolParam
from openai.types.responses.response_create_params import ResponseCreateParamsBase
from watcher_litellm.callback import SESSION_PREFIX

# LiteLLM model parameters per provider route. Each is reached through the
# gateway and exposed by the proxy under its route name.
ROUTES: dict[str, dict[str, Any]] = {
    "openai": {"model": "openai/gpt-5.4-mini", "api_base": f"{GATEWAY}/v1"},
    "anthropic": {"model": "anthropic/claude-haiku-4-5", "api_base": GATEWAY},
    "gemini": {
        "model": "gemini/gemini-2.5-flash",
        "api_base": f"{GATEWAY}/v1/projects/{GOOGLE_PROJECT}/locations/global/publishers/google",
    },
    "openrouter-qwen": {"model": "openai/qwen/qwen3-coder", "api_base": f"{GATEWAY}/v1"},
    "openrouter-grok": {"model": "openai/x-ai/grok-4.6", "api_base": f"{GATEWAY}/v1"},
}
# The Gemini route needs the gateway's Vertex project; leave it out without one.
_DEFAULT_ROUTES = ",".join(name for name in ROUTES if name != "gemini" or GOOGLE_PROJECT)
SELECTED = [name for name in os.environ.get("WATCHER_LIVE_ROUTES", _DEFAULT_ROUTES).split(",") if name]
APIS = ["chat_completions", "responses", "messages"]
SCHEMAS: dict[str, dict[str, object]] = {
    "read_file": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]},
    "delete_all_files": {"type": "object", "properties": {"confirm": {"type": "boolean"}}, "required": ["confirm"]},
}
PROMPTS = {
    "read_file": "Read the file notes.txt using the read_file tool.",
    "delete_all_files": "Delete every file now by calling delete_all_files with confirm set to true.",
}


@pytest.fixture(scope="module")
def live_proxy(live_policy: None, tmp_path_factory: pytest.TempPathFactory) -> Iterator[str]:
    model_list = [{"model_name": name, "litellm_params": {**ROUTES[name], "api_key": GATEWAY_KEY}} for name in SELECTED]
    env = {"WATCHER_API_URL": str(WATCHER_URL), "WATCHER_API_KEY": os.environ.get("WATCHER_LIVE_API_KEY", "")}
    with litellm_proxy(model_list, env, tmp_path_factory.mktemp("live-proxy")) as url:
        yield url


class Conversation:
    """One client conversation through the proxy in a single API, with a Watcher session header."""

    def __init__(self, proxy_url: str, api: str, route: str, stream: bool) -> None:
        self.api, self.route, self.stream = api, route, stream
        self.session_id = f"litellm-live-{uuid.uuid4()}"
        headers = {"x-watcher-session-id": self.session_id}
        self.anthropic = anthropic.Anthropic(
            base_url=proxy_url, api_key="sk-proxy", default_headers=headers, max_retries=0
        )
        self.openai = openai.OpenAI(
            base_url=f"{proxy_url}/v1", api_key="sk-proxy", default_headers=headers, max_retries=0
        )
        self.history: list[Any] = []

    def ask(self, tool: str) -> tuple[str, list[dict[str, Any]]]:
        """Send the tool prompt, forcing that tool; return reply text and client tool calls."""
        self.history = [{"role": "user", "content": PROMPTS[tool]}]
        return self._send(force=tool)

    def answer(self, calls: list[dict[str, Any]], result: str) -> tuple[str, list[dict[str, Any]]]:
        """Return a tool result for each call and let the model finish in text."""
        if self.api == "messages":
            self.history.append(
                {
                    "role": "user",
                    "content": [{"type": "tool_result", "tool_use_id": c["id"], "content": result} for c in calls],
                }
            )
        elif self.api == "responses":
            self.history.extend({"type": "function_call_output", "call_id": c["id"], "output": result} for c in calls)
        else:
            self.history.extend({"role": "tool", "tool_call_id": c["id"], "content": result} for c in calls)
        return self._send(force=None)

    def _send(self, force: str | None) -> tuple[str, list[dict[str, Any]]]:
        if self.api == "messages":
            kwargs: dict[str, Any] = {
                "model": self.route,
                "max_tokens": 1024,
                "messages": self.history,
                "tools": [
                    {"name": name, "description": name, "input_schema": schema} for name, schema in SCHEMAS.items()
                ],
            }
            if force:
                kwargs["tool_choice"] = {"type": "tool", "name": force}
            if self.stream:
                with self.anthropic.messages.stream(**kwargs) as events:
                    message = events.get_final_message()
            else:
                message = self.anthropic.messages.create(**kwargs)
            content = [block.model_dump(exclude_none=True) for block in message.content]
            self.history.append({"role": "assistant", "content": content})
            calls = [
                {"id": b["id"], "name": b["name"], "input": b["input"]} for b in content if b["type"] == "tool_use"
            ]
            return "".join(b.get("text", "") for b in content if b["type"] == "text"), calls
        if self.api == "responses":
            # LiteLLM cannot stream Responses to non-OpenAI providers with a
            # named tool_choice (it fails validating its own completed event),
            # so offer only the forced tool and require a call instead.
            named_choice = not (self.stream and not self.route.startswith("openai"))
            offered = SCHEMAS if named_choice or not force else {force: SCHEMAS[force]}
            # Keep strict omitted in the request; the SDK's tool stub requires it.
            response_kwargs: ResponseCreateParamsBase = {
                "model": self.route,
                "input": self.history,
                "store": False,
                "tools": [
                    cast(FunctionToolParam, {"type": "function", "name": name, "parameters": schema})
                    for name, schema in offered.items()
                ],
            }
            if force:
                response_kwargs["tool_choice"] = {"type": "function", "name": force} if named_choice else "required"
            if self.stream:
                with self.openai.responses.stream(**response_kwargs) as events:
                    response = events.get_final_response()
            else:
                response = self.openai.responses.create(**response_kwargs)
            output = [item.model_dump(exclude_none=True) for item in response.output]
            self.history.extend(item for item in output if item["type"] in ("message", "function_call"))
            calls = [
                {"id": item["call_id"], "name": item["name"], "input": json.loads(item["arguments"])}
                for item in output
                if item["type"] == "function_call"
            ]
            return response.output_text, calls
        chat_kwargs: CompletionCreateParamsBase = {
            "model": self.route,
            "messages": self.history,
            "tools": [
                {"type": "function", "function": {"name": name, "parameters": schema}}
                for name, schema in SCHEMAS.items()
            ],
        }
        if force:
            chat_kwargs["tool_choice"] = {"type": "function", "function": {"name": force}}
        if self.stream:
            with self.openai.chat.completions.stream(**chat_kwargs) as events:
                completion = events.get_final_completion()
        else:
            completion = self.openai.chat.completions.create(**chat_kwargs)
        message = completion.choices[0].message
        self.history.append(message.model_dump(exclude_none=True, exclude={"parsed"}))
        calls = []
        for call in message.tool_calls or []:
            assert call.type == "function", "The live fixture only declares function tools"
            calls.append({"id": call.id, "name": call.function.name, "input": json.loads(call.function.arguments)})
        return message.content or "", calls

    def recorded(self, min_messages: int = 0) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        """Watcher's session and decided tool calls for this conversation."""
        return recorded_calls({"other": [SESSION_PREFIX + self.session_id]}, min_messages=min_messages)


@pytest.mark.parametrize("stream", [False, True], ids=["json", "stream"])
@pytest.mark.parametrize("api", APIS)
@pytest.mark.parametrize("route", SELECTED)
def test_denied_tool_is_withheld_and_recorded(live_proxy: str, route: str, api: str, stream: bool) -> None:
    conversation = Conversation(live_proxy, api, route, stream)

    text, calls = conversation.ask("delete_all_files")

    assert calls == []
    assert "Watcher withheld the proposed tool call" in text
    _, recorded = conversation.recorded()
    assert [(c["tool_name"], c["applied_decision"]) for c in recorded] == [("delete_all_files", "deny")]


@pytest.mark.parametrize("stream", [False, True], ids=["json", "stream"])
@pytest.mark.parametrize("api", APIS)
@pytest.mark.parametrize("route", SELECTED)
def test_allowed_tool_runs_and_the_conversation_continues(live_proxy: str, route: str, api: str, stream: bool) -> None:
    conversation = Conversation(live_proxy, api, route, stream)

    _, calls = conversation.ask("read_file")
    assert [call["name"] for call in calls] == ["read_file"]
    text, more_calls = conversation.answer(calls, "The notes say: remember the milk.")

    assert more_calls == [] and "milk" in text.lower()
    session, recorded = conversation.recorded(min_messages=4)
    assert [(c["tool_name"], c["applied_decision"], c["tool_use_id"]) for c in recorded] == [
        ("read_file", "allow", calls[0]["id"])
    ]
    assert session["message_count"] >= 4
