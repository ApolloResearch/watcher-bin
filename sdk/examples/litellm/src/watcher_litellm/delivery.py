"""Deliver one incremental client response across gateway resampling attempts.

The callback validates and grades provider events with ``IncrementalStream``.
It passes only releasable events to ``StreamDelivery``, which preserves that
ordering while removing attempt boundaries. Replaying complete replacement
bodies would delay text unnecessarily and duplicate content already delivered.

1. Forward safe content immediately and assign global block/tool/item indices.
2. On denial, retain late events for already visible items, then add a notice.
3. Append the next attempt's safe content under the original response identity.
4. Emit one terminal envelope whose output is exactly the delivered content.

    attempt 1: text -> allowed call -> [denied call, withheld tail]
                  +-----------------------+
    attempt 2: text -> allowed alternative +-> one client response

Usage belongs to the first provider attempt; it is not an estimate of total
retry cost. Responses item completion payloads remain authoritative, including
opaque reasoning fields that a terminal snapshot may encrypt differently.
"""

from typing import Any
from uuid import uuid4

import litellm

from watcher_litellm.incremental import IncrementalStream, PendingEvent, is_client_item, wire_event
from watcher_litellm.streams import API, IncompleteStream, UnsupportedStream, as_dict, assemble


def compose_nonstream(
    api: API,
    original: dict[str, Any],
    replacement: dict[str, Any] | None,
    notice: str,
) -> dict[str, Any]:
    """Replace all original client calls with a notice and an approved alternative.

    Use only after grading every replacement call. Unlike streaming, none of
    the original calls have reached the client, so all are removed together.
    Messages/Responses retain content preceding the first client call; Chat's
    scalar text has no relative tool ordering and is retained in full. Original
    identity and usage survive, as do signed and opaque retained content fields.

    Unknown populated Chat fields and unsupported block/item shapes fail closed
    rather than losing information while combining replies. Inputs are detached
    before editing. A missing replacement terminates with the notice alone.
    """
    if not notice:
        raise UnsupportedStream("A delivery notice must not be empty")
    result = as_dict(original)
    alternative = as_dict(replacement) if replacement is not None else None
    try:
        if api == "chat_completions":
            return _compose_chat(result, alternative, notice)
        field = "content" if api == "messages" else "output"
        blocks = result[field]
        additions = alternative[field] if alternative is not None else []
        allowed_types = (
            {"text", "thinking", "redacted_thinking", "tool_use", "server_tool_use", "web_search_tool_result"}
            if api == "messages"
            else {
                "message",
                "reasoning",
                "function_call",
                "custom_tool_call",
                "local_shell_call",
                "tool_search_call",
                "web_search_call",
                "file_search_call",
                "code_interpreter_call",
                "image_generation_call",
                "mcp_call",
                "mcp_list_tools",
                "mcp_approval_request",
            }
        )
        if any(block["type"] not in allowed_types for block in [*blocks, *additions]):
            raise UnsupportedStream("Unsupported content in a resampled response")
        if api == "responses" and any(
            block["type"] == "tool_search_call" and block.get("execution") != "client"
            for block in [*blocks, *additions]
        ):
            raise UnsupportedStream("Only client-executed tool searches can be composed")
        cut = next(
            (
                index
                for index, block in enumerate(blocks)
                if (block["type"] == "tool_use" if api == "messages" else is_client_item(block))
            ),
            len(blocks),
        )
        if api == "messages":
            result[field] = [*blocks[:cut], {"type": "text", "text": notice}, *additions]
            reason = alternative.get("stop_reason", "end_turn") if alternative is not None else "end_turn"
            if reason in {"end_turn", "tool_use"} and any(block["type"] == "tool_use" for block in additions):
                reason = "tool_use"
            result.update(
                stop_reason=reason, stop_sequence=alternative.get("stop_sequence") if alternative is not None else None
            )
            result.pop("stop_details", None)
            if alternative is not None and alternative.get("stop_details"):
                result["stop_details"] = alternative["stop_details"]
            if alternative is not None and "container" in alternative:
                result["container"] = alternative["container"]
        else:
            text = {
                "id": f"msg_{uuid4().hex}",
                "type": "message",
                "role": "assistant",
                "status": "completed",
                "content": [{"type": "output_text", "text": notice, "annotations": [], "logprobs": []}],
            }
            result[field] = [*blocks[:cut], text, *additions]
            item_ids: set[str] = set()
            call_ids: set[str] = set()
            for item in result[field]:
                StreamDelivery._unique(item["id"], item_ids)
                if is_client_item(item):
                    StreamDelivery._unique(item["call_id"], call_ids)
            result["status"] = alternative["status"] if alternative is not None else "completed"
            for key in ("incomplete_details", "error"):
                result[key] = alternative.get(key) if alternative is not None else None
        return result
    except (KeyError, IndexError, TypeError, AttributeError) as exc:
        raise UnsupportedStream("Malformed resampled response") from exc


def _compose_chat(original: dict[str, Any], replacement: dict[str, Any] | None, notice: str) -> dict[str, Any]:
    """Combine scalar Chat fields without guessing how multimodal or extension fields merge."""
    message_fields = {"role", "content", "tool_calls", "function_call", "reasoning_content", "refusal"}
    empty_defaults = {"annotations": [[]], "provider_specific_fields": [{}, {"refusal": None}]}
    for response in [original, *([replacement] if replacement is not None else [])]:
        if len(response["choices"]) != 1 or response["choices"][0]["index"] != 0:
            raise UnsupportedStream("Only one Chat choice can be composed")
        message = response["choices"][0]["message"]
        if message["role"] != "assistant" or any(
            key not in message_fields
            and value is not None
            and not (key in empty_defaults and value in empty_defaults[key])
            for key, value in message.items()
        ):
            raise UnsupportedStream("Unsupported Chat message fields in a resampled response")
        if any(
            message.get(key) is not None and not isinstance(message[key], str)
            for key in ("content", "reasoning_content", "refusal")
        ):
            raise UnsupportedStream("Chat resampling requires scalar content")
    choice = original["choices"][0]
    message = choice["message"]
    other = replacement["choices"][0]["message"] if replacement is not None else {}
    message["content"] = "\n\n".join(part for part in [message.get("content"), notice, other.get("content")] if part)
    for key in ("reasoning_content", "refusal"):
        if message.get(key) or other.get(key):
            message[key] = (message.get(key) or "") + (other.get(key) or "")
    for key in ("tool_calls", "function_call"):
        message.pop(key, None)
        if other.get(key):
            message[key] = other[key]
    reason = replacement["choices"][0]["finish_reason"] if replacement is not None else "stop"
    if reason in {"stop", "tool_calls", "function_call"} and message.get("tool_calls"):
        reason = "tool_calls"
    elif reason in {"stop", "tool_calls", "function_call"} and message.get("function_call"):
        reason = "function_call"
    choice["finish_reason"] = reason
    # Token-indexed probabilities from the rejected answer cannot describe the
    # merged message. Unlike usage, they would misidentify generated content.
    choice.pop("logprobs", None)
    return original


class StreamDelivery:
    """Compose safe events without exposing denied calls or restarting the client stream.

    Call ``begin_attempt`` before each provider stream. Pass parsed, releasable
    frames to ``emit`` after updating the parser's ``allowed`` set. Following a
    denial, drain the provider and emit only frames selected by ``retains``;
    this closes interleaved items that the client has already seen. Checkpoint
    the completed attempt, add a notice, then begin a replacement attempt.

    ``finish`` emits the sole terminal event and populates ``response`` for
    recording. It requires every visible block/item to have completed. Index
    gaps are removed, but item and call IDs are preserved; collisions between
    delivered attempts fail closed. Instances are single-use and request-local.
    """

    def __init__(self, api: API) -> None:
        self.api: API = api
        self.response: dict[str, Any] = {}
        self._envelope: dict[str, Any] = {}
        self._attempt_envelope: dict[str, Any] = {}
        self._original: dict[str, Any] = {}
        self._message_usage: dict[str, Any] = {}
        self._indices: dict[int, int] = {}
        self._items: list[dict[str, Any]] = []
        self._open: set[int] = set()
        self._item_ids: set[str] = set()
        self._call_ids: set[str] = set()
        self._chat_chunks: list[Any] = []
        self._chat_usage: dict[str, Any] | None = None
        self._chat_usage_separate = False
        self._chat_usage_emitted = False
        self._chat_has_text = False
        self._chat_notice_needs_separator = False
        self._legacy = False
        self._attempt = 0
        self._sequence = 0
        self._started = False
        self._finished = False

    def begin_attempt(self) -> None:
        """Reset local indices after draining the previous attempt's visible items.

        A new attempt cannot repair a partially delivered item. Starting one
        while a retained item remains open raises ``IncompleteStream``.
        """
        self._ensure_closed()
        if self._finished:
            raise UnsupportedStream("Delivery has already finished")
        self._indices = {}
        self._attempt_envelope = {}
        self._attempt += 1

    def retains(self, frame: PendingEvent) -> bool:
        """Select late content/closures of visible items while draining a denied attempt.

        Metadata and terminal frames are also selected so usage can be captured;
        ``emit`` suppresses their attempt completion. New items, unexposed calls
        and unindexed Chat text after the denied call are not retained.
        """
        data = frame.data
        if self.api == "chat_completions":
            choices = data["choices"]
            if not choices:
                return True
            delta = choices[0]["delta"]
            calls = delta.get("tool_calls") or []
            if calls:
                return all(call["index"] in self._indices for call in calls)
            if delta.get("function_call"):
                return 0 in self._indices
            return not any(value not in (None, "", [], {}) for value in delta.values())
        if self.api == "messages":
            return data.get("index") in self._indices or data["type"] in {"ping", "message_delta", "message_stop"}
        return data.get("output_index") in self._indices or data["type"] in {
            "response.completed",
            "response.incomplete",
        }

    def emit(self, frame: PendingEvent, state: IncrementalStream) -> list[bytes]:
        """Forward a validated safe frame, remapping indices and suppressing terminal events.

        The parser may have advanced beyond this buffered frame. Final item
        content is read only at block/item completion; deltas always remain
        incremental. A frame that exposes a call absent from ``state.allowed``
        fails closed even if the callback accidentally releases it.
        """
        if not self._attempt or state.api != self.api:
            raise UnsupportedStream("Invalid delivery lifecycle")
        data = as_dict(frame.data)
        if self._finished:
            if self.api != "chat_completions":
                raise UnsupportedStream("Delivery has already finished")
            return self._late_chat_usage(data)
        if self.api == "chat_completions":
            return self._chat(data, frame, state)
        kind = data["type"]
        if kind in {"message_delta", "message_stop", "response.completed", "response.incomplete"}:
            if kind == "message_delta" and self._attempt == 1:
                self._message_usage.update(data.get("usage") or {})
            return []
        if not frame.requires <= state.allowed:
            raise UnsupportedStream("Cannot deliver an unevaluated tool call")
        if self.api == "messages":
            return self._messages(data, state)
        return self._responses(data)

    def checkpoint(self, state: IncrementalStream) -> None:
        """Capture the first completed provider envelope, including its original usage.

        Denied calls may remain unapproved in the parser, but the provider must
        have reached a valid terminal event. Later attempts do not overwrite
        the first attempt's identity, metadata or accounting.
        """
        if not state.terminal:
            raise IncompleteStream("Cannot checkpoint an unfinished provider response")
        for key in ("id", "model"):
            if key in self._attempt_envelope and state.body.get(key) != self._attempt_envelope[key]:
                raise UnsupportedStream("Provider response identity changed during its stream")
        if self.api == "chat_completions" and self._indices:
            # A call's source may have completed while some of its interleaved
            # fragments are still behind a denied call in the callback FIFO.
            # All those approved fragments must survive draining before retry.
            completed = [*self._chat_chunks, litellm.ModelResponseStream(**self._chat_event({}, "stop"))]
            message = assemble(self.api, completed)["choices"][0]["message"]
            if self._legacy:
                if message.get("function_call") != state.chat_legacy:
                    raise IncompleteStream("A delivered legacy Chat call is still incomplete")
            elif any(
                message["tool_calls"][global_index] != state.chat_calls[local]
                for local, global_index in self._indices.items()
            ):
                raise IncompleteStream("A delivered Chat call is still incomplete")
        if not self._original:
            self._original = as_dict(state.body)

    def notice(self, text: str) -> list[bytes]:
        """Append an ordinary assistant text notice after all visible items have closed.

        Chat separates notices from adjacent nonempty text with paragraph breaks;
        other APIs use separate text blocks. This never emits an executable call
        or invents a result for an already allowed call.
        """
        self._ensure_closed()
        if not self._started or self._finished or not text:
            raise UnsupportedStream("Cannot append a notice before starting or after finishing")
        if self.api == "chat_completions":
            if self._chat_has_text:
                text = "\n\n" + text
            delta = {"content": text} if self._chat_chunks else {"role": "assistant", "content": text}
            event = self._chat_event(delta, None)
            self._chat_chunks.append(litellm.ModelResponseStream(**event))
            self._chat_has_text = True
            self._chat_notice_needs_separator = True
            return [wire_event(self.api, event)]
        index = len(self._items)
        if self.api == "messages":
            block = {"type": "text", "text": text}
            self._items.append(block)
            return [
                wire_event(self.api, event)
                for event in [
                    {"type": "content_block_start", "index": index, "content_block": {"type": "text", "text": ""}},
                    {"type": "content_block_delta", "index": index, "delta": {"type": "text_delta", "text": text}},
                    {"type": "content_block_stop", "index": index},
                ]
            ]
        item_id = f"msg_{uuid4().hex}"
        self._unique(item_id, self._item_ids)
        part = {"type": "output_text", "text": text, "annotations": [], "logprobs": []}
        item = {"id": item_id, "type": "message", "role": "assistant", "status": "completed", "content": [part]}
        self._items.append(item)
        location = {"output_index": index, "content_index": 0, "item_id": item_id}
        return [
            self._response_event(event)
            for event in [
                {
                    "type": "response.output_item.added",
                    "output_index": index,
                    "item": {**item, "status": "in_progress", "content": []},
                },
                {"type": "response.content_part.added", **location, "part": {**part, "text": ""}},
                {"type": "response.output_text.delta", **location, "delta": text, "logprobs": []},
                {"type": "response.output_text.done", **location, "text": text, "logprobs": []},
                {"type": "response.content_part.done", **location, "part": part},
                {"type": "response.output_item.done", "output_index": index, "item": item},
            ]
        ]

    def finish(self, state: IncrementalStream) -> list[bytes]:
        """Complete the merged response once; earlier approved calls retain tool stop reasons.

        The final attempt may itself be denied after exhausting the retry
        budget. Only delivered calls affect the client stop reason or output.
        The proxy remains responsible for Chat's final ``[DONE]`` sentinel.
        """
        self._ensure_closed()
        if not self._started or self._finished:
            raise UnsupportedStream("Cannot finish an unstarted or finished delivery")
        self.checkpoint(state)
        self._finished = True
        if self.api == "chat_completions":
            return self._finish_chat(state)
        self.response = as_dict(self._original)
        if self.api == "messages":
            reason = state.body.get("stop_reason") or "end_turn"
            if self._call_ids and reason in {"end_turn", "tool_use"}:
                reason = "tool_use"
            elif reason == "tool_use":
                reason = "end_turn"
            stop = {
                "stop_reason": reason,
                "stop_sequence": state.body.get("stop_sequence") if reason == "stop_sequence" else None,
            }
            self.response.pop("stop_details", None)
            if state.body.get("stop_details"):
                stop["stop_details"] = state.body["stop_details"]
            if "container" in state.body:
                stop["container"] = state.body["container"]
            self.response.update(content=as_dict({"items": self._items})["items"], **stop)
            return [
                wire_event(self.api, {"type": "message_delta", "delta": stop, "usage": self._message_usage}),
                wire_event(self.api, {"type": "message_stop"}),
            ]
        status = state.body["status"]
        if status not in {"completed", "incomplete"}:
            raise UnsupportedStream("Invalid final Responses status")
        self.response.update(output=as_dict({"items": self._items})["items"], status=status)
        for key in ("incomplete_details", "error"):
            if key in state.body:
                self.response[key] = state.body[key]
        return [self._response_event({"type": f"response.{status}", "response": self.response})]

    def error(self, code: str, message: str, status: int) -> bytes:
        """End an interrupted stream with the API's error shape and ordered sequence number."""
        if self.api == "messages":
            kind = "overloaded_error" if status >= 500 else "invalid_request_error"
            return wire_event(self.api, {"type": "error", "error": {"type": kind, "message": message}})
        if self.api == "responses":
            return self._response_event({"type": "error", "code": code, "message": message, "param": None})
        return wire_event(self.api, {"error": {"type": code, "code": code, "message": message}})

    def _messages(self, data: dict[str, Any], state: IncrementalStream) -> list[bytes]:
        """Preserve Messages block ordering and snapshot completed block content."""
        kind = data["type"]
        if kind == "message_start":
            self._attempt_envelope = as_dict(data["message"])
            if self._started:
                return []
            self._envelope = as_dict(data["message"])
            self._started = True
        elif kind == "content_block_start":
            block = data["content_block"]
            if block["type"] == "tool_use":
                self._unique(block["id"], self._call_ids)
            self._start_item(data["index"], block)
        if "index" in data:
            local = data["index"]
            data["index"] = self._indices[local]
            if kind == "content_block_stop":
                self._items[data["index"]] = as_dict(state.body["content"][local])
                self._open.remove(data["index"])
        return [wire_event(self.api, data)]

    def _responses(self, data: dict[str, Any]) -> list[bytes]:
        """Keep one response identity while reindexing interleaved retained output items."""
        kind = data["type"]
        if kind in {"response.created", "response.in_progress", "response.queued"}:
            if not self._attempt_envelope:
                self._attempt_envelope = as_dict(data["response"])
            elif any(data["response"].get(key) != self._attempt_envelope.get(key) for key in ("id", "model")):
                raise UnsupportedStream("Provider response identity changed during its stream")
            if self._attempt > 1:
                return []
            if not self._started:
                self._envelope = as_dict(data["response"])
                self._started = True
            return [self._response_event(data)]
        local = data["output_index"]
        if kind == "response.output_item.added":
            item = data["item"]
            self._unique(item["id"], self._item_ids)
            if is_client_item(item):
                self._unique(item.get("call_id") or item["id"], self._call_ids)
            self._start_item(local, item)
        data["output_index"] = self._indices[local]
        if kind == "response.output_item.done":
            self._items[data["output_index"]] = as_dict(data["item"])
            self._open.remove(data["output_index"])
        return [self._response_event(data)]

    def _chat(self, data: dict[str, Any], frame: PendingEvent, state: IncrementalStream) -> list[bytes]:
        """Remap fragmented Chat calls and capture original usage without exposing completion."""
        if not self._attempt_envelope:
            self._attempt_envelope = {key: value for key, value in data.items() if key not in {"choices", "usage"}}
        elif any(data.get(key) != self._attempt_envelope.get(key) for key in ("id", "model")):
            raise UnsupportedStream("Provider response identity changed during its stream")
        if not self._started:
            self._envelope = {key: value for key, value in data.items() if key not in {"choices", "usage"}}
            self._started = True
        choices = data["choices"]
        if self._attempt == 1 and data.get("usage") is not None:
            self._chat_usage = as_dict(data["usage"])
            self._chat_usage_separate = not choices
        if not choices:
            return []
        choice = choices[0]
        delta = choice["delta"]
        if not any(value not in (None, "", [], {}) for value in delta.values()) and not choice.get("logprobs"):
            return []
        if not frame.requires <= state.allowed:
            raise UnsupportedStream("Cannot deliver an unevaluated tool call")
        if self._attempt > 1:
            delta.pop("role", None)
        if not self._chat_chunks:
            delta.setdefault("role", "assistant")
        for call in delta.get("tool_calls") or []:
            if self._legacy:
                raise UnsupportedStream("Cannot compose legacy and modern Chat calls")
            local = call["index"]
            if local not in self._indices:
                self._unique(state.chat_calls[local]["id"], self._call_ids)
                self._indices[local] = len(self._call_ids) - 1
            call["index"] = self._indices[local]
        if delta.get("function_call") and 0 not in self._indices:
            if self._call_ids or self._legacy:
                raise UnsupportedStream("Cannot compose multiple legacy Chat calls")
            self._legacy = True
            self._indices[0] = 0
        event: dict[str, Any] = {
            **data,
            **self._envelope,
            "choices": [{**choice, "delta": delta, "finish_reason": None}],
        }
        event.pop("usage", None)
        output: list[bytes] = []
        if delta.get("content"):
            if self._chat_notice_needs_separator:
                # Keep synthetic whitespace separate from provider deltas so
                # token-indexed logprobs still describe the original content.
                separator = self._chat_event({"content": "\n\n"}, None)
                self._chat_chunks.append(litellm.ModelResponseStream(**separator))
                output.append(wire_event(self.api, separator))
            self._chat_notice_needs_separator = False
            self._chat_has_text = True
        self._chat_chunks.append(litellm.ModelResponseStream(**event))
        return [*output, wire_event(self.api, event)]

    def _finish_chat(self, state: IncrementalStream) -> list[bytes]:
        """Reconstruct only emitted Chat deltas and emit original usage exactly once."""
        reason = state.body["choices"][0]["finish_reason"]
        if self._call_ids and reason in {"stop", "tool_calls", "function_call"}:
            reason = "tool_calls"
        elif self._legacy and reason in {"stop", "tool_calls", "function_call"}:
            reason = "function_call"
        elif reason in {"tool_calls", "function_call"}:
            reason = "stop"
        terminal = self._chat_event({}, reason)
        if self._chat_usage is not None and not self._chat_usage_separate:
            terminal["usage"] = self._chat_usage
        self._chat_chunks.append(litellm.ModelResponseStream(**terminal))
        body = assemble(self.api, self._chat_chunks)
        self.response = {**as_dict(self._original), "choices": body["choices"]}
        if self._chat_usage is not None:
            self.response["usage"] = as_dict(self._chat_usage)
        output = [wire_event(self.api, terminal)]
        if self._chat_usage is not None and self._chat_usage_separate:
            output.append(wire_event(self.api, {**self._envelope, "choices": [], "usage": self._chat_usage}))
        self._chat_usage_emitted = self._chat_usage is not None
        return output

    def _late_chat_usage(self, data: dict[str, Any]) -> list[bytes]:
        """Allow original accounting after prompt completion without a second finish marker.

        Standard Chat streaming can send usage after the choice finishes.
        Replacement usage remains private because the merged envelope promises
        the original attempt's accounting. No content may follow completion.
        """
        if any(
            choice.get("finish_reason") or any(value not in (None, "", [], {}) for value in choice["delta"].values())
            for choice in data["choices"]
        ):
            raise UnsupportedStream("Chat content continued after delivery finished")
        if any(data.get(key) != self._attempt_envelope.get(key) for key in ("id", "model")):
            raise UnsupportedStream("Provider response identity changed during its stream")
        if self._attempt != 1 or self._chat_usage_emitted or data.get("usage") is None:
            return []
        self._chat_usage = as_dict(data["usage"])
        self.response["usage"] = as_dict(self._chat_usage)
        self._chat_usage_emitted = True
        return [wire_event(self.api, {**data, **self._envelope})]

    def _start_item(self, local: int, item: dict[str, Any]) -> None:
        if not self._started or local in self._indices:
            raise UnsupportedStream("Invalid delivery item start")
        index = len(self._items)
        self._indices[local] = index
        self._items.append(as_dict(item))
        self._open.add(index)

    def _ensure_closed(self) -> None:
        if self._open:
            raise IncompleteStream("A delivered item is still incomplete")

    @staticmethod
    def _unique(identity: str, seen: set[str]) -> None:
        if not identity or identity in seen:
            raise UnsupportedStream("Missing or duplicate delivered item/call ID")
        seen.add(identity)

    def _response_event(self, data: dict[str, Any]) -> bytes:
        data = {**data, "sequence_number": self._sequence}
        self._sequence += 1
        return wire_event(self.api, data)

    def _chat_event(self, delta: dict[str, Any], reason: str | None) -> dict[str, Any]:
        return {**self._envelope, "choices": [{"index": 0, "delta": delta, "finish_reason": reason}]}
