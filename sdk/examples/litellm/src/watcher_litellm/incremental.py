"""Validate streaming events and identify the earliest safe tool-evaluation boundary.

The callback owns asynchronous I/O; ``IncrementalStream`` owns protocol state.
Every outgoing event carries the calls it exposes. A FIFO in the callback holds
that event and everything behind it until those calls are allowed. This preserves
interleaved event order without letting a later, faster call overtake an earlier
one. Messages completes a call at block stop, Responses at item done, and Chat
at choice finish: Chat has no per-call completion marker, and valid JSON alone
does not prove that the provider has finished appending arguments or a name.

    provider -> validated event -> [blocked call | later events] -> client
                                       |
                               completed call -> Watcher

Each evaluation includes one new call. Previously evaluated response content
becomes assistant history in a private request copy, so Watcher's raw hook does
not select and bill the earlier calls again. These synthetic exchanges describe
the same ordered conversation; they are never sent back to the model provider.
"""

import json
from typing import Any

from pydantic import BaseModel, Field

from watcher_litellm.streams import (
    API,
    MESSAGES_EVENT_TYPES,
    IncompleteStream,
    MessageAssembler,
    UnsupportedStream,
    as_dict,
    assemble,
)

PROVIDER_ITEMS = frozenset(
    {
        "web_search_call",
        "file_search_call",
        "code_interpreter_call",
        "image_generation_call",
        "mcp_call",
        "mcp_list_tools",
        "mcp_approval_request",
    }
)

# These fields determine the executable operation. Canonical JSON comparisons
# distinguish JSON booleans from integers even inside decoded tool-search inputs.
_CLIENT_CALL_FIELDS = (
    "type",
    "id",
    "call_id",
    "name",
    "arguments",
    "input",
    "namespace",
    "caller",
    "action",
    "execution",
)


def _same_call(first: dict[str, Any], second: dict[str, Any]) -> bool:
    """Require unchanged executable fields at item completion and response completion."""
    return json.dumps(
        {key: first.get(key) for key in _CLIENT_CALL_FIELDS}, sort_keys=True, allow_nan=False
    ) == json.dumps({key: second.get(key) for key in _CLIENT_CALL_FIELDS}, sort_keys=True, allow_nan=False)


def is_client_item(item: dict[str, Any]) -> bool:
    """Whether a Responses item asks the client, rather than its provider, to execute a tool."""
    kind = item["type"]
    return kind.endswith("_call") and kind not in PROVIDER_ITEMS


def wire_event(api: API, event: dict[str, Any]) -> bytes:
    """Encode a detached, validated event; never forward unparsed provider bytes."""
    prefix = "" if api == "chat_completions" else f"event: {event['type']}\n"
    return f"{prefix}data: {json.dumps(event, ensure_ascii=False)}\n\n".encode()


class PendingEvent(BaseModel):
    """An event and the tool indices that must be approved before it can leave the FIFO."""

    data: dict[str, Any]
    requires: set[int] = Field(default_factory=set)


class Evaluation(BaseModel):
    """One complete call with preceding approved content moved into request history."""

    request: dict[str, Any]
    response: dict[str, Any]


class IncrementalStream:
    """Per-request parser and call inventory, independent of network scheduling.

    ``add`` validates and returns events to enqueue. ``ready`` identifies the
    next complete unapproved call in first-appearance order. After a successful
    ``evaluation``, the caller adds its index to ``allowed``. Call indices never
    change, and completed executable fields cannot be amended. ``finish`` rejects
    truncated streams even if an earlier approved call was already delivered.
    """

    def __init__(self, api: API) -> None:
        self.api = api
        self.calls: list[int] = []
        self.ids: set[str] = set()
        self.complete: set[int] = set()
        self.allowed: set[int] = set()
        self.terminal = False
        self.body: dict[str, Any] = {}
        self.messages = MessageAssembler()
        self.items: list[dict[str, Any]] = []
        self.done_items: set[int] = set()
        self.chat_chunks: list[Any] = []
        self.chat_calls: dict[int, dict[str, Any]] = {}
        self.chat_legacy: dict[str, Any] | None = None

    def _register(self, index: int, call_id: str) -> None:
        if not call_id or call_id in self.ids:
            raise UnsupportedStream("Missing or duplicate tool call ID")
        self.calls.append(index)
        self.ids.add(call_id)

    def add(self, value: Any) -> list[PendingEvent]:
        """Validate one decoded event before exposing any part of it to the client.

        Malformed provider data fails closed. Unknown Messages events are ignored,
        matching Anthropic's forward-compatible event contract; unknown Responses
        events fail closed because they may introduce a new executable item shape.
        """
        try:
            data = as_dict(value)
            if self.api == "messages":
                return self._messages(data)
            if self.api == "responses":
                return self._responses(data)
            return self._chat(value, data)
        except (KeyError, IndexError, TypeError, AttributeError, ValueError) as exc:
            raise UnsupportedStream("Malformed provider stream") from exc

    def _messages(self, data: dict[str, Any]) -> list[PendingEvent]:
        kind = data["type"]
        # Anthropic's SDK stream accumulator requires message_start as its first
        # event. Gateway keepalives are SSE comments; upstream pings can arrive
        # earlier and carry no content that needs to reach the client.
        if kind == "ping" and self.messages.message is None:
            return []
        if kind == "message_start" and data["message"].get("content"):
            raise UnsupportedStream("Messages start contains unstreamed content")
        if kind == "content_block_start":
            block = data["content_block"]
            if block["type"] == "fallback":
                raise UnsupportedStream("A fallback cannot retract already streamed content")
            if block["type"] == "tool_use":
                self._register(data["index"], block["id"])
        self.messages.add(json.dumps(data))
        if kind not in MESSAGES_EVENT_TYPES:
            return []
        if self.messages.message is not None:
            self.body = self.messages.message
        index = data.get("index")
        if kind == "content_block_stop" and index in self.calls:
            self.complete.add(index)
        self.terminal = self.messages.stopped
        needs = {index} if index in self.calls else set()
        if kind in {"message_delta", "message_stop"}:
            needs = set(self.calls)
        return [PendingEvent(data=data, requires=needs)]

    def _chat(self, value: Any, data: dict[str, Any]) -> list[PendingEvent]:
        if data.get("error"):
            raise IncompleteStream("Chat stream reported an error")
        choices = data["choices"]
        if len(choices) > 1 or (choices and choices[0]["index"] != 0):
            raise UnsupportedStream("Only one Chat choice can be evaluated")
        if self.terminal:
            if any(
                choice.get("finish_reason")
                or any(value not in (None, "", [], {}) for value in choice["delta"].values())
                for choice in choices
            ):
                raise UnsupportedStream("Chat choice continued after its finish reason")
            return [PendingEvent(data=data)]
        needs: set[int] = set()
        for choice in choices:
            delta = choice["delta"]
            for call in delta.get("tool_calls") or []:
                index = call["index"]
                if index not in self.chat_calls:
                    if index != len(self.chat_calls) or self.chat_legacy is not None:
                        raise UnsupportedStream("Chat tool indices are not sequential")
                    self.chat_calls[index] = {"id": "", "type": "function", "function": {"name": "", "arguments": ""}}
                    self.calls.append(index)
                if call.get("type") not in (None, "function"):
                    raise UnsupportedStream("Unsupported Chat tool type")
                target = self.chat_calls[index]
                target["id"] += call.get("id") or ""
                for key in ("name", "arguments"):
                    target["function"][key] += (call.get("function") or {}).get(key) or ""
                needs.add(index)
            if delta.get("function_call"):
                if self.chat_calls:
                    raise UnsupportedStream("Mixed legacy and modern Chat calls")
                if self.chat_legacy is None:
                    self.chat_legacy = {"name": "", "arguments": ""}
                    self._register(0, "function_call")
                for key in ("name", "arguments"):
                    self.chat_legacy[key] += delta["function_call"].get(key) or ""
                needs.add(0)
        self.chat_chunks.append(value)
        if choices and choices[0].get("finish_reason"):
            self.body = assemble("chat_completions", self.chat_chunks)
            message = self.body["choices"][0]["message"]
            calls = message.get("tool_calls") or []
            if calls != list(self.chat_calls.values()):
                raise UnsupportedStream("Chat assembly disagrees with streamed calls")
            ids = [call["id"] for call in calls]
            if len(set(ids)) != len(ids) or any(not call_id for call_id in ids):
                raise UnsupportedStream("Missing or duplicate Chat call IDs")
            if self.chat_legacy is not None and message.get("function_call") != self.chat_legacy:
                raise UnsupportedStream("Chat assembly disagrees with its legacy call")
            self.complete.update(self.calls)
            self.terminal = True
            needs.update(self.calls)
        if not choices or not (choices[0]["delta"].get("tool_calls") or choices[0]["delta"].get("function_call")):
            return [PendingEvent(data=data, requires=needs)]
        return self._split_chat_event(data)

    @staticmethod
    def _split_chat_event(data: dict[str, Any]) -> list[PendingEvent]:
        """Separate coalesced text/calls so one transport chunk does not create a false barrier.

        Chat delta fields have no relative wire ordering. Emit their non-tool
        content first, then each tool in its original array order. Finish reason,
        log probabilities and usage are emitted once, never duplicated per call.
        """
        choice = data["choices"][0]
        delta = choice["delta"]
        envelope = {key: value for key, value in data.items() if key not in {"choices", "usage"}}

        def frame(fragment: dict[str, Any], requires: set[int]) -> PendingEvent:
            return PendingEvent(
                data={**envelope, "choices": [{"index": 0, "delta": fragment, "finish_reason": None}]},
                requires=requires,
            )

        frames: list[PendingEvent] = []
        text = {key: value for key, value in delta.items() if key not in {"tool_calls", "function_call"}}
        if any(value not in (None, "", [], {}) for value in text.values()):
            frames.append(frame(text, set()))
        for call in delta.get("tool_calls") or []:
            frames.append(frame({"tool_calls": [call]}, {call["index"]}))
        if delta.get("function_call"):
            frames.append(frame({"function_call": delta["function_call"]}, {0}))
        if choice.get("finish_reason") or data.get("usage") or choice.get("logprobs"):
            final = as_dict(data)
            final["choices"][0]["delta"] = {}
            frames.append(PendingEvent(data=final))
        return frames

    def _responses(self, data: dict[str, Any]) -> list[PendingEvent]:
        kind = data["type"]
        if self.terminal:
            raise UnsupportedStream("Responses continued after its terminal event")
        if kind in {"error", "response.failed"}:
            raise IncompleteStream("Responses reported an error")
        if kind in {"response.created", "response.in_progress", "response.queued"}:
            body = data["response"]
            if body.get("output"):
                raise UnsupportedStream("Responses metadata contains unstreamed output")
            if kind == "response.created" and self.body:
                raise UnsupportedStream("Responses started twice")
            self.body = {**body, "output": self.items}
            return [PendingEvent(data=data)]
        if not self.body:
            raise UnsupportedStream("Responses has no creation event")
        if kind in {"response.completed", "response.incomplete"}:
            final = data["response"]
            if len(final["output"]) != len(self.items) or self.done_items != set(range(len(self.items))):
                raise IncompleteStream("Responses has unfinished or unstreamed items")
            for index, item in enumerate(final["output"]):
                if is_client_item(item) or index in self.calls:
                    if not _same_call(item, self.items[index]):
                        raise UnsupportedStream("Responses terminal changed an evaluated call")
            self.body = as_dict(final)
            self.terminal = True
            return [PendingEvent(data=data, requires=set(self.calls))]
        index = data["output_index"]
        if kind == "response.output_item.added":
            if index != len(self.items):
                raise UnsupportedStream("Responses item indices are not sequential")
            item = as_dict(data["item"])
            if is_client_item(item):
                if item["type"] not in {"function_call", "custom_tool_call", "local_shell_call", "tool_search_call"}:
                    raise UnsupportedStream("Unsupported client tool type")
                if item["type"] == "tool_search_call" and item.get("execution") != "client":
                    raise UnsupportedStream("Only client-executed tool searches can be evaluated")
                self._register(index, item.get("call_id") or item["id"])
            self.items.append(item)
        else:
            if index in self.done_items:
                raise UnsupportedStream("Responses item changed after completion")
            item = self.items[index]
            if data.get("item_id") not in (None, item["id"]):
                raise UnsupportedStream("Responses event item identity changed")
            if kind == "response.output_item.done":
                final = data["item"]
                if item["id"] != final["id"] or item["type"] != final["type"]:
                    raise UnsupportedStream("Responses item identity changed")
                if index in self.calls:
                    if not _same_call(item, final):
                        raise UnsupportedStream("Responses done changed streamed call fields")
                    self.complete.add(index)
                self.items[index] = as_dict(final)
                self.done_items.add(index)
            elif index in self.calls:
                # Shell actions and deferred-tool searches arrive as whole
                # items. Inventing an argument delta interpretation would let
                # the released item disagree with the operation Watcher saw.
                if item["type"] not in {"function_call", "custom_tool_call"}:
                    raise UnsupportedStream("Unexpected delta for a whole-item client tool")
                field = "arguments" if item["type"] == "function_call" else "input"
                family = "function_call_arguments" if field == "arguments" else "custom_tool_call_input"
                if kind == f"response.{family}.delta":
                    item[field] = item.get(field, "") + data["delta"]
                elif kind == f"response.{family}.done":
                    if item.get(field, "") != data[field] or data.get("name", item["name"]) != item["name"]:
                        raise UnsupportedStream("Responses done changed streamed arguments")
                else:
                    raise UnsupportedStream("Unexpected event for a client tool")
            elif kind == "response.content_part.added":
                if data["content_index"] != len(item["content"]):
                    raise UnsupportedStream("Responses content indices are not sequential")
                item["content"].append(as_dict(data["part"]))
            elif kind == "response.output_text.delta":
                item["content"][data["content_index"]]["text"] += data["delta"]
            elif kind == "response.refusal.delta":
                item["content"][data["content_index"]]["refusal"] += data["delta"]
            elif kind == "response.content_part.done":
                item["content"][data["content_index"]] = as_dict(data["part"])
            elif not self._safe_item_event(kind, item):
                raise UnsupportedStream("Unsupported Responses event")
        self.body["output"] = self.items
        return [PendingEvent(data=data, requires={index} if index in self.calls else set())]

    @staticmethod
    def _safe_item_event(kind: str, item: dict[str, Any]) -> bool:
        """Recognize non-executable event families without allowing call deltas on text items."""
        if item["type"] == "message":
            return kind in {
                "response.output_text.done",
                "response.output_text.annotation.added",
                "response.refusal.done",
            }
        if item["type"] == "reasoning":
            return kind.startswith(("response.reasoning_", "response.reasoning."))
        return item["type"] in PROVIDER_ITEMS and kind.startswith(
            (f"response.{item['type']}.", f"response.{item['type']}_")
        )

    def ready(self) -> int | None:
        """The first unapproved call, but only after its protocol completion boundary."""
        for index in self.calls:
            if index not in self.allowed:
                return index if index in self.complete else None
        return None

    def evaluation(self, request: dict[str, Any], index: int | None) -> Evaluation:
        """Build one-call raw exchange, or a text-only tail for background recording.

        Earlier approved calls become assistant history, never new calls. A copy
        is mandatory: LiteLLM and the original provider request share their input.
        """
        request = as_dict(request)
        body = as_dict(self.body)
        previous = max(self.allowed, default=-1) + 1
        if self.api == "chat_completions":
            message = body["choices"][0]["message"]
            history = as_dict(message)
            calls = message.get("tool_calls") or []
            history["tool_calls"] = calls[:previous]
            message["tool_calls"] = calls[previous : index + 1] if index is not None else []
            if previous:
                request["messages"] = [*(request.get("messages") or []), history]
                message["content"] = None
            if self.chat_legacy is not None and index is None:
                message.pop("function_call", None)
        elif self.api == "messages":
            if previous:
                request["messages"] = [
                    *(request.get("messages") or []),
                    {"role": "assistant", "content": body["content"][:previous]},
                ]
            body["content"] = body["content"][previous : index + 1] if index is not None else body["content"][previous:]
            if index is not None:
                body["stop_reason"] = "tool_use"
        else:
            if previous:
                prior_input = request.get("input") or []
                if isinstance(prior_input, str):
                    prior_input = [{"role": "user", "content": prior_input}]
                request["input"] = [*prior_input, *body["output"][:previous]]
            body["output"] = body["output"][previous : index + 1] if index is not None else body["output"][previous:]
        return Evaluation(request=request, response=body)

    def finish(self) -> None:
        """Refuse EOF without a protocol terminator or with incomplete/unapproved calls."""
        if not self.terminal or set(self.calls) != self.allowed:
            raise IncompleteStream("Provider stream ended before completing its calls")
