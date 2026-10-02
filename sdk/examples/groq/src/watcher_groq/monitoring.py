"""Gate application function callbacks using original buffered provider exchanges."""

import asyncio
import json
from copy import deepcopy

from watcher_groq.integration import fetch
from watcher_groq.raw import Withheld, evaluate, inventory


class Monitor:
    """Apply inherited Watcher policy before executing a native tool batch.

    All calls must be registered and allowed before any side effect. Reused IDs
    are rejected within this instance, including after a failed authorization.
    Escalations remain withheld; this helper has no human approval interface.
    Tool results are kept in native history and reach Watcher with the next real
    provider pair. Keep that history if the conversation stops or generation fails.
    """

    def __init__(self, watcher, session_id, *, timeout=420, enforcement="server"):
        if not session_id or timeout <= 0 or enforcement not in {"server", "enforce", "observe", "paused"}:
            raise ValueError("A conversation ID, positive timeout and supported mode are required")
        self.watcher, self.session_id = watcher, session_id
        self.timeout, self.enforcement = timeout, enforcement
        self.attempted = set()
        self.lock = asyncio.Lock()

    async def dispatch(self, exchange, functions):
        """Authorize every exact native call, then return linked native tool results.

        Caller mutation cannot change the submitted batch. Ordinary function errors
        become linked error strings; cancellation propagates and is never retried.
        This instance is not a durable exactly-once execution mechanism.
        """
        exchange = deepcopy(exchange)
        pending = list(inventory(exchange["response"], "chat_completions").values())
        async with self.lock:
            identifiers = {item["tool_use_id"] for item in pending}
            if identifiers & self.attempted:
                raise Withheld("Repeated execution identity")
            self.attempted.update(identifiers)
            if any(item["tool_name"] not in functions for item in pending):
                raise Withheld("Unregistered function")
            callbacks = [functions[item["tool_name"]] for item in pending]
            await evaluate(
                self.watcher,
                **exchange,
                provider="groq",
                api="chat_completions",
                session_id=self.session_id,
                enforcement=self.enforcement,
                timeout=self.timeout,
            )
            results = []
            for item, callback in zip(pending, callbacks, strict=True):
                try:
                    value = await callback(**deepcopy(item["tool_input"]))
                    content = json.dumps(value, ensure_ascii=False)
                except Exception as error:
                    content = json.dumps({"error": type(error).__name__})
                results.append({"role": "tool", "tool_call_id": item["tool_use_id"], "content": content})
            return results


async def run_turn(client, monitor, *, model, messages, functions, tools=None):
    """Generate buffered proposals, gate them, and return complete native history.

    Feed the returned history into the next turn unchanged. This never invents a
    provider response to flush results. Model generation is outside the tool gate.
    """
    request = {"model": model, "messages": deepcopy(messages)}
    if tools is not None:
        request["tools"] = deepcopy(tools)
    _, exchange = await fetch(client, request)
    results = await monitor.dispatch(exchange, functions)
    return [*exchange["request"]["messages"], deepcopy(exchange["response"]["choices"][0]["message"]), *results]
