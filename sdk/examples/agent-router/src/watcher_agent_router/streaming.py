"""Gate a streamed Chat Completions response on Watcher decisions without delaying its text.

Envoy hands the processor a server-sent event (SSE) stream in arbitrary byte
chunks. Chat Completions has no marker for when one tool call's argument
fragments are complete, so a call is only known in full once the provider ends
the stream. ``StreamGate`` therefore:

1. rewrites every line ending (CR, LF or CRLF, as SSE allows) to LF and splits
   the bytes into complete events, keeping an incomplete tail until the rest
   arrives. The client receives the rewritten bytes, so it parses exactly the
   events checked here and never half an event;
2. releases complete events as they arrive until the first one carrying a tool
   call (or legacy function call) delta;
3. holds that event and everything after it until the provider ends the stream,
   and always holds the ``[DONE]`` terminator: clients stop reading at it, so
   releasing it early would let them disconnect before the exchange is
   submitted;
4. assembles the parsed chunks into one ``chat.completion`` body for Watcher,
   which the caller evaluates before releasing or replacing the held events.

Clients stop at ``[DONE]`` and treat a choice as complete at its
``finish_reason``, so data after either is refused rather than assembled: it
could change the call Watcher grades without changing the one delivered.

::

    provider bytes ──► complete events ──► text-only so far? ──yes──► client now
                                               │no (tool delta seen)
                                               ▼
                                        held until end of stream ──► Watcher
"""

import json

from watcher_agent_router.exchange import UnsupportedExchange, decode_json

# After line endings are rewritten to LF, each SSE event ends with a blank line.
_EVENT_END = b"\n\n"
# Largest usage object echoed into a synthesized denial; real ones are a few hundred bytes.
_USAGE_LIMIT = 4096
# Streamed text fields besides content that a buffered assistant message carries.
_TEXT_FIELDS = ("refusal", "reasoning", "reasoning_content")
# Fields of one reasoning_details entry that arrive as successive fragments.
_DETAIL_TEXT = ("text", "summary", "data")


class StreamGate:
    """Track one streamed response: what may be released now and what is held for Watcher."""

    def __init__(self, max_bytes: int) -> None:
        self._max_bytes = max_bytes
        self._tail = b""
        # A CR at the end of a chunk may be the first half of a CRLF.
        self._pending_cr = False
        self._held = bytearray()
        self._total = 0
        self._done = False
        self._finished = False
        self.holding = False
        self.released_text = False
        self.released_role = False
        self.chunks: list[dict] = []

    def feed(self, data: bytes, final: bool = False) -> bytes:
        """Accept the next provider bytes; return the complete events that may go to the client now.

        ``final`` marks the end of the provider stream, where a trailing CR can
        no longer start a CRLF and is a line ending in its own right.
        """
        self._total += len(data)
        if self._total > self._max_bytes:
            raise UnsupportedExchange("The streamed response exceeds the size limit")
        if self._pending_cr:
            data = b"\r" + data
        self._pending_cr = data.endswith(b"\r") and not final
        if self._pending_cr:
            data = data[:-1]
        buffer = self._tail + data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
        end = buffer.rfind(_EVENT_END)
        if end < 0:
            self._tail = buffer
            return b""
        complete, self._tail = buffer[: end + len(_EVENT_END)], buffer[end + len(_EVENT_END) :]
        released = bytearray()
        for event in complete.split(_EVENT_END)[:-1]:
            raw = event + _EVENT_END
            kind = self._record(event)
            if kind == "tool":
                self.holding = True
            if self.holding or kind == "done":
                self._held += raw
            else:
                released += raw
        return bytes(released)

    def release_held(self) -> bytes:
        """Return every held event plus any unterminated tail, once Watcher has allowed them."""
        held, self._held = bytes(self._held) + self._tail + (b"\n" if self._pending_cr else b""), bytearray()
        self._tail, self._pending_cr = b"", False
        return held

    def _record(self, event: bytes) -> str:
        """Parse one event's data like an OpenAI client; return ``tool``, ``done`` or ``other``."""
        lines = [line[5:] for line in event.split(b"\n") if line.startswith(b"data:")]
        payload = b"\n".join(line[1:] if line.startswith(b" ") else line for line in lines)
        if not lines:
            return "other"
        if self._done:
            raise UnsupportedExchange("The stream continued after its terminator")
        if payload.startswith(b"[DONE]"):
            self._done = True
            return "done"
        chunk = decode_json(payload)
        if not isinstance(chunk, dict):
            raise UnsupportedExchange("Stream event data must be a JSON object")
        if "error" in chunk:
            raise UnsupportedExchange("The provider reported an error in the stream")
        self.chunks.append(chunk)
        choices = chunk.get("choices")
        if choices is None:
            choices = []
        if not isinstance(choices, list):
            raise UnsupportedExchange("Invalid stream choices")
        # Clients read choices[0]; a second entry, even with index 0, would be
        # merged into what Watcher grades without being delivered.
        if len(choices) > 1:
            raise UnsupportedExchange("Exactly one streamed choice is required")
        if choices and self._finished:
            raise UnsupportedExchange("The stream continued after its choice finished")
        if any(isinstance(choice, dict) and choice.get("finish_reason") is not None for choice in choices):
            self._finished = True
        proposes = any(
            isinstance(choice, dict)
            and isinstance(choice.get("delta"), dict)
            and (choice["delta"].get("tool_calls") or choice["delta"].get("function_call"))
            for choice in choices
        )
        if not proposes and not self.holding:
            deltas = [
                choice["delta"]
                for choice in choices
                if isinstance(choice, dict) and isinstance(choice.get("delta"), dict)
            ]
            self.released_text = self.released_text or any(delta.get("content") for delta in deltas)
            # OpenAI's stream accumulator concatenates a repeated role, so it is sent once.
            self.released_role = self.released_role or any(delta.get("role") for delta in deltas)
        return "tool" if proposes else "other"

    def completion(self) -> dict:
        """Assemble the streamed chunks into the ``chat.completion`` body the client effectively received.

        Content, refusal, reasoning and argument fragments are concatenated in
        order (``reasoning_details`` lists are joined); each tool call is keyed
        by its ``index``. A choice other than index 0 or a
        legacy function call is kept so the delivery inventory rejects it.
        """
        if self._tail.strip():
            raise UnsupportedExchange("The stream ended inside an event")
        message: dict = {"role": "assistant", "content": None}
        calls: dict[int, dict] = {}
        details: list[dict] = []
        finish_reason = None
        usage = None
        first: dict = {}
        for chunk in self.chunks:
            first = first or chunk
            if chunk.get("usage") is not None:
                usage = chunk["usage"]
            for choice in chunk.get("choices") or []:
                if not isinstance(choice, dict) or choice.get("index") != 0:
                    raise UnsupportedExchange("Exactly one streamed choice is required")
                delta = choice.get("delta") or {}
                if not isinstance(delta, dict):
                    raise UnsupportedExchange("Invalid stream delta")
                if delta.get("function_call") is not None:
                    message["function_call"] = delta["function_call"]
                if isinstance(delta.get("content"), str):
                    message["content"] = (message["content"] or "") + delta["content"]
                # The text fields Watcher's converter reads from a buffered message,
                # so a streamed refusal or reasoning trace is graded too.
                for key in _TEXT_FIELDS:
                    if isinstance(delta.get(key), str):
                        message[key] = message.get(key, "") + delta[key]
                for detail in _items(delta.get("reasoning_details"), "reasoning details"):
                    _merge_detail(details, detail)
                for fragment in _items(delta.get("tool_calls"), "tool calls"):
                    _merge_call(calls, fragment)
                if choice.get("finish_reason") is not None:
                    finish_reason = choice["finish_reason"]
        if calls:
            message["tool_calls"] = [calls[index] for index in sorted(calls)]
        if details:
            message["reasoning_details"] = details
        completion = {
            "id": first.get("id"),
            "object": "chat.completion",
            "created": first.get("created"),
            "model": first.get("model"),
            "choices": [{"index": 0, "message": message, "finish_reason": finish_reason}],
        }
        if usage is not None:
            completion["usage"] = usage
        return completion

    def denial_events(self, notice: str, alternative: dict | None = None) -> bytes:
        """Events that end the stream normally after Watcher refused a call.

        The held events are dropped, so no refused call reaches the client;
        the client sees an ordinary assistant message instead of an error:
        the notice as text, then any approved ``alternative`` (a buffered
        completion that passed ``alternative_message``) as its text and
        complete tool calls, then the alternative's finish reason or ``stop``.
        """
        first = self.chunks[0] if self.chunks else {}
        # Echoed provider identifiers are shortened so the replacement stays small.
        base = {
            "id": str(first.get("id", ""))[:256],
            "object": "chat.completion.chunk",
            "created": first.get("created") if type(first.get("created")) is int else 0,
            "model": str(first.get("model", ""))[:256],
        }
        other = alternative["choices"][0]["message"] if alternative is not None else {}
        text = "\n\n".join(part for part in (notice, other.get("content")) if part)
        delta: dict = {"content": "\n\n" + text if self.released_text else text}
        for key in ("refusal", "reasoning_content"):
            if other.get(key):
                delta[key] = other[key]
        if not self.released_role:
            delta = {"role": "assistant", **delta}
        events = [{**base, "choices": [{"index": 0, "delta": delta, "finish_reason": None}]}]
        reason = alternative["choices"][0]["finish_reason"] if alternative is not None else "stop"
        if other.get("tool_calls"):
            calls = [
                {"index": index, "id": call["id"], "type": "function", "function": call["function"]}
                for index, call in enumerate(other["tool_calls"])
            ]
            events.append({**base, "choices": [{"index": 0, "delta": {"tool_calls": calls}, "finish_reason": None}]})
            reason = "tool_calls"
        events.append({**base, "choices": [{"index": 0, "delta": {}, "finish_reason": reason}]})
        # A client that asked for usage (stream_options.include_usage) still gets
        # it; ordinary usage is tiny, and anything larger is dropped to keep the
        # replacement within its size budget.
        usage = [chunk["usage"] for chunk in self.chunks if chunk.get("usage") is not None]
        if usage and len(_compact(usage[-1])) <= _USAGE_LIMIT:
            events.append({**base, "choices": [], "usage": usage[-1]})
        return b"".join(b"data: " + _compact(event) + _EVENT_END for event in events) + b"data: [DONE]" + _EVENT_END


def _compact(value: object) -> bytes:
    """Serialize synthesized JSON without padding or escapes, so it is no larger than needed."""
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode()


def _items(value: object, label: str) -> list:
    """Return a streamed list field; absent or null is empty, any other type is refused."""
    if value is None:
        return []
    if not isinstance(value, list):
        raise UnsupportedExchange(f"Invalid streamed {label}")
    return value


def _merge_call(calls: dict[int, dict], fragment: object) -> None:
    """Append one streamed tool-call fragment to the call with the same index."""
    if not isinstance(fragment, dict) or type(fragment.get("index")) is not int:
        raise UnsupportedExchange("Invalid streamed tool call")
    call = calls.setdefault(fragment["index"], {"id": None, "type": None, "function": {"name": "", "arguments": ""}})
    for key in ("id", "type"):
        if fragment.get(key) is not None:
            if call[key] not in (None, fragment[key]):
                raise UnsupportedExchange("A streamed tool call changed its identity")
            call[key] = fragment[key]
    function = fragment.get("function") or {}
    if not isinstance(function, dict):
        raise UnsupportedExchange("Invalid streamed tool function")
    for key in ("name", "arguments"):
        if function.get(key) is not None:
            if not isinstance(function[key], str):
                raise UnsupportedExchange("Invalid streamed tool function")
            call["function"][key] += function[key]


def _merge_detail(details: list[dict], fragment: object) -> None:
    """Join one streamed ``reasoning_details`` fragment to the entry with the same index.

    OpenRouter-style providers split one reasoning block over many chunks that
    share an ``index``; Watcher's converter reads each entry's text as one
    block, so fragments are concatenated rather than kept as separate entries.
    """
    if not isinstance(fragment, dict):
        raise UnsupportedExchange("Invalid streamed reasoning detail")
    index = fragment.get("index")
    entry = next((item for item in details if index is not None and item.get("index") == index), None)
    if entry is None:
        details.append(dict(fragment))
        return
    for key, value in fragment.items():
        if key in _DETAIL_TEXT and isinstance(value, str) and isinstance(entry.get(key), str):
            entry[key] += value
        elif entry.get(key) is None:
            entry[key] = value


def error_event(message: str, conversation_id: str, status: int) -> bytes:
    """An SSE event that OpenAI clients raise as an error, ending the delivered stream.

    ``status`` is the HTTP status a buffered response would have had: 403 for a
    refusal, 503 when Watcher was unavailable.
    """
    error = {"message": message, "type": "watcher_withheld", "code": status, "conversation_id": conversation_id}
    return b"data: " + json.dumps({"error": error}).encode() + _EVENT_END
