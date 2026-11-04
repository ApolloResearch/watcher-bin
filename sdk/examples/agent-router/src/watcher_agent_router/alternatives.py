"""Ask the model for alternatives to a refused proposal, through the same gateway.

When Watcher denies a proposal, the processor shows the model its refused
calls as tool results and asks for another proposal, at most twice per client
request. After an escalation, or a third refused proposal, it asks instead for
one final reply with tool calls disabled, in which the model puts the question
to the user (texts in ``notices.py``). Each generation is an ordinary request
to Agent Router's listener, so it uses the same route, backend and provider
credentials as the client's request. Every alternative is graded as its own
exchange before any of it reaches the client; calls in the final reply are
withheld without grading.

That request passes through this processor again. Grading it there as well
would grade every alternative twice and start a nested recovery, so the
processor marks it with ``X-Watcher-Alternative``: an expiry and an HMAC over
the expiry and the exact request body, keyed from the Watcher API key, which
clients and providers never see. A request with a valid marker skips grading in
the nested pass; the outer pass grades the alternative itself. The marker is
removed before the request reaches Agent Router's backend.

::

    client ──► gateway ──► processor: proposal refused
                              │  continuation + marker
                              ▼
                gateway ──► processor (marker valid: pass through) ──► provider
                              │  alternative
                              ▼
               processor: grade alternative as a new Watcher session
                              │
                              ▼
    client ◄── original text + refusal notices + approved alternative or final reply

Everything shares the time limit of the first evaluation, which stays below
Envoy's message timeout. A failed or timed-out alternative never releases a
call: the client receives the notices with a sentence saying why no
alternative followed.
"""

import asyncio
import hashlib
import hmac
import json
import re
import time
from uuid import uuid4

import httpx
import structlog
from pydantic import BaseModel, ConfigDict

from watcher_agent_router.exchange import (
    CHAT_COMPLETIONS_PATH,
    CONVERSATION_PREFIX,
    Denial,
    Evaluation,
    UnsupportedExchange,
    alternative_message,
    client_calls,
    decode_json,
    evaluate,
    operation_key,
)
from watcher_agent_router.notices import ALTERNATIVE_FAILED, continuation, stop_notice, withheld_notice
from watcher_sdk import AsyncWatcherClient, WatcherAPIError

ALTERNATIVE_HEADER = "x-watcher-alternative"
# The client's proposal plus at most two alternatives, as in the LiteLLM example; a final
# text-only reply follows the last refusal.
MAX_PROPOSALS = 3
_KEY_LABEL = b"watcher-agent-router alternative marker v1"
# A Unix-seconds expiry and a SHA-256 hex digest; anything else is rejected
# before parsing, so hostile values cannot raise during verification.
_MARKER = re.compile(r"([0-9]{1,12})\.([0-9a-f]{64})")

logger = structlog.get_logger(__name__)


def marker_key(watcher_api_key: str) -> bytes:
    """Derive the marker key from the Watcher API key, which every processor replica shares."""
    return hmac.new(watcher_api_key.encode(), _KEY_LABEL, hashlib.sha256).digest()


def _mac(key: bytes, expiry: int, body: bytes) -> str:
    return hmac.new(key, f"{expiry}.".encode() + hashlib.sha256(body).digest(), hashlib.sha256).hexdigest()


def sign_marker(key: bytes, body: bytes, expiry: int) -> str:
    """Mark one alternative request body as the processor's own until ``expiry`` (Unix seconds)."""
    return f"{expiry}.{_mac(key, expiry, body)}"


def verify_marker(key: bytes, marker: str, body: bytes, now: float | None = None) -> bool:
    """True when ``marker`` was signed for exactly ``body`` and has not expired; malformed markers are False."""
    match = _MARKER.fullmatch(marker)
    if match is None or int(match[1]) < (time.time() if now is None else now):
        return False
    return hmac.compare_digest(match[2], _mac(key, int(match[1]), body))


class AlternativeFailed(Exception):
    """No alternative could be obtained; the message is fixed text shown to the client."""


class Gateway(BaseModel):
    """Agent Router's client listener, used to generate alternatives with the gateway client key."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    client: httpx.AsyncClient
    client_key: str
    marker_key: bytes
    max_body: int

    async def generate(self, request: dict, deadline: float) -> dict:
        """Send one continuation through the gateway and return the provider's completion.

        ``deadline`` is on the event loop clock; the marker expires with it.
        The body is read incrementally up to ``max_body`` and must arrive
        uncompressed, so a small compressed reply cannot expand in memory.
        Non-2xx statuses, encoded, oversized or unreadable bodies
        raise ``AlternativeFailed``; nothing here grades the result.
        """
        body = json.dumps(request, ensure_ascii=False, separators=(",", ":")).encode()
        if len(body) > self.max_body:
            raise AlternativeFailed("the conversation is too long to ask for an alternative")
        remaining = deadline - asyncio.get_running_loop().time()
        marker = sign_marker(self.marker_key, body, int(time.time() + remaining) + 1)
        headers = {
            "content-type": "application/json",
            "accept-encoding": "identity",
            "x-api-key": self.client_key,
            ALTERNATIVE_HEADER: marker,
        }
        try:
            async with self.client.stream("POST", CHAT_COMPLETIONS_PATH, content=body, headers=headers) as reply:
                # Like the client path, any success status may carry a completion.
                if not 200 <= reply.status_code < 300:
                    logger.warning("alternative_request_failed", status=reply.status_code)
                    raise AlternativeFailed("the provider did not return an alternative")
                if reply.headers.get("content-encoding", "identity").strip().lower() != "identity":
                    raise AlternativeFailed("the provider returned a compressed alternative")
                data = bytearray()
                # Identity encoding is required above, so these are the bytes as sent.
                async for chunk in reply.aiter_bytes():
                    data += chunk
                    if len(data) > self.max_body:
                        raise AlternativeFailed("the alternative exceeds the size limit")
        except httpx.HTTPError as error:
            logger.warning("alternative_request_failed", error_type=type(error).__name__)
            raise AlternativeFailed("the gateway could not be reached") from None
        try:
            response = decode_json(bytes(data))
        except UnsupportedExchange:
            raise AlternativeFailed("the provider did not return an alternative") from None
        if not isinstance(response, dict):
            raise AlternativeFailed("the provider did not return an alternative")
        return response


class Recovery(BaseModel):
    """What the client receives after a refusal: notices, and an approved alternative or final reply if one was found.

    ``alternative`` is a completion whose calls Watcher allowed, or the final
    text-only reply that asks the user how to proceed; either way every call
    it carries may be delivered. ``question`` is the fixed question that ends
    the reply when it must be shortened to fit the size limit, so a shortened
    reply still asks the user how to proceed; it is unset when no
    alternatives were requested.
    """

    notices: list[str]
    alternative: dict | None = None
    question: str | None = None


def _repeats(response: dict, forbidden: dict[str, Denial]) -> list[Denial]:
    """Calls in ``response`` that repeat a refused operation under any call ID, with the earlier refusal.

    A new call ID must not give a refused operation another chance at a
    stochastic policy decision, so repeats are refused without grading, and
    keep the earlier escalation and whether the user may approve it.
    """
    calls = response["choices"][0]["message"].get("tool_calls") or []
    repeats = []
    for call in calls:
        arguments = decode_json(call["function"]["arguments"])
        earlier = forbidden.get(operation_key(call["function"]["name"], arguments))
        if earlier is not None:
            repeats.append(earlier.model_copy(update={"tool_use_id": call["id"], "tool_input": arguments}))
    return repeats


async def recover(
    watcher: AsyncWatcherClient,
    gateway: Gateway | None,
    request: dict,
    response: dict,
    evaluation: Evaluation,
    *,
    conversation_id: str,
    user_agent: str | None,
    deadline: float,
) -> Recovery:
    """Look for an approved alternative to a refused proposal, or a final reply, within ``deadline``.

    Each blocked proposal adds its notice. After a denial the model is asked
    for another approach, with at most three proposals in all (the client's
    and two alternatives). After an escalation, or the third blocked
    proposal, one final generation, with tool calls disabled, asks the model
    to stop and put the question to the user. So at most four model calls
    serve one client request, and only the first three can release calls.

    Without a ``gateway`` only the first notice is returned. After a failed
    generation a sentence says why nothing followed and a fixed question asks
    the user how to proceed; nothing from that attempt is delivered.
    """
    notices = [withheld_notice(response, evaluation)]
    if gateway is None:
        return Recovery(notices=notices)
    forbidden: dict[str, Denial] = {}
    for attempt in range(1, MAX_PROPOSALS + 1):
        forbidden.update({operation_key(d.tool_name, d.tool_input): d for d in evaluation.denials})
        stop = attempt == MAX_PROPOSALS or any(denial.is_escalation for denial in evaluation.denials)
        request = continuation(request, response, evaluation, stop=stop)
        if stop:
            final = await _final(
                gateway, request, evaluation.denials, conversation_id=conversation_id, deadline=deadline
            )
            question = stop_notice(evaluation.denials)
            if isinstance(final, str):
                notices += [f"No final reply was delivered because {final}.", question]
                return Recovery(notices=notices, question=question)
            return Recovery(notices=notices, alternative=final, question=question)
        outcome = await _alternative(
            watcher,
            gateway,
            request,
            forbidden,
            conversation_id=conversation_id,
            user_agent=user_agent,
            deadline=deadline,
            attempt=attempt,
        )
        if isinstance(outcome, str):
            notices += [f"No alternative was delivered because {outcome}.", ALTERNATIVE_FAILED]
            return Recovery(notices=notices, question=ALTERNATIVE_FAILED)
        response, evaluation = outcome
        if not evaluation.denials:
            if not client_calls(response) and _asks_nothing(response):
                # A text-only alternative with no text, or cut off by a limit or
                # filter, would end the agent's turn without a question.
                response = _closed(response, ALTERNATIVE_FAILED)
            return Recovery(notices=notices, alternative=response, question=ALTERNATIVE_FAILED)
        notices.append(withheld_notice(response, evaluation))
    raise AssertionError("the final generation always returns")  # pragma: no cover


async def _final(
    gateway: Gateway, request: dict, refusals: list[Denial], *, conversation_id: str, deadline: float
) -> dict | str:
    """Generate the final reply that asks the user how to proceed; return it, or why it failed.

    ``request`` already disables tool calls where it offers tools. A model
    that proposes calls anyway is not graded: the reply was meant to be text,
    so every call is withheld, and ``stop_notice`` for ``refusals`` (the
    refusals that led here) is appended to its text to put the question to
    the user. The same question is appended to a reply that does not ask the
    user anything: one with no text, one cut off by the token limit or the
    provider's content filter, or one whose text has no question mark. That
    reply would otherwise end the agent's turn with nobody asked how to
    proceed. A complete reply that already asks is returned unchanged, so the
    question is not repeated. The returned reason is fixed text for the client.
    """
    try:
        async with asyncio.timeout_at(deadline):
            response = await gateway.generate(request, deadline)
        withheld = client_calls(response)
        alternative_message(response)
    except TimeoutError:
        return "the time limit was reached"
    except AlternativeFailed as error:
        return str(error)
    except UnsupportedExchange as error:
        logger.warning("final_reply_unverifiable", conversation_id=conversation_id, check=str(error))
        return "the gateway cannot verify the reply"
    logger.info("final_reply", conversation_id=conversation_id, withheld=len(withheld))
    if not withheld and _asks_user(response):
        return response
    return _closed(response, stop_notice(refusals))


def _asks_user(response: dict) -> bool:
    """Whether a complete reply already asks the user something: its text carries a question mark.

    A missing question mark is a cheap, conservative signal: a reply without
    one gets the fixed question, while one that asks in its own words is left
    alone rather than asked twice.
    """
    return not _asks_nothing(response) and "?" in response["choices"][0]["message"]["content"]


def _asks_nothing(response: dict) -> bool:
    """Whether a reply's text cannot carry a question: it is blank, or cut off by the token limit or content filter."""
    choice = response["choices"][0]
    return not (choice["message"].get("content") or "").strip() or choice["finish_reason"] in {
        "length",
        "content_filter",
    }


def _closed(response: dict, question: str) -> dict:
    """``response`` without tool calls, its text followed by ``question``, ending normally."""
    choice = response["choices"][0]
    message = dict(choice["message"])
    message.pop("tool_calls", None)
    message["content"] = "\n\n".join(part for part in (message.get("content"), question) if part)
    return {**response, "choices": [{**choice, "message": message, "finish_reason": "stop"}]}


async def _alternative(
    watcher: AsyncWatcherClient,
    gateway: Gateway,
    request: dict,
    forbidden: dict[str, Denial],
    *,
    conversation_id: str,
    user_agent: str | None,
    deadline: float,
    attempt: int,
) -> tuple[dict, Evaluation] | str:
    """Generate and grade one alternative; return it with its verified evaluation, or why it failed.

    The alternative is graded under a fresh ``agent-router:`` conversation ID,
    with ``request`` (the continuation that produced it) as its history. The
    returned reason is fixed text for the client, never provider content.
    """
    alternative_id = f"{CONVERSATION_PREFIX}{uuid4()}"
    try:
        async with asyncio.timeout_at(deadline):
            response = await gateway.generate(request, deadline)
            client_calls(response)
            alternative_message(response)
            repeats = _repeats(response, forbidden)
            if repeats:
                # Refused locally: nothing is submitted, so no Watcher session exists for it.
                logger.info("alternative_repeated", conversation_id=conversation_id, attempt=attempt)
                return response, Evaluation(verified=True, denials=repeats)
            evaluation = await evaluate(
                watcher, request, response, conversation_id=alternative_id, user_agent=user_agent
            )
    except TimeoutError:
        return "the time limit was reached"
    except AlternativeFailed as error:
        return str(error)
    except UnsupportedExchange as error:
        logger.warning("alternative_unverifiable", conversation_id=conversation_id, check=str(error))
        return "the gateway cannot verify the alternative"
    except WatcherAPIError as error:
        logger.warning("alternative_not_evaluated", conversation_id=conversation_id, watcher_status=error.status_code)
        return "Watcher did not evaluate the alternative"
    except Exception as error:
        logger.warning("alternative_not_evaluated", conversation_id=conversation_id, error_type=type(error).__name__)
        return "Watcher did not evaluate the alternative"
    logger.info(
        "alternative_evaluated",
        conversation_id=conversation_id,
        alternative_conversation_id=alternative_id,
        attempt=attempt,
        verified=evaluation.verified,
        denied=len(evaluation.denials),
    )
    if not evaluation.verified:
        return "Watcher's decisions do not match the alternative"
    return response, evaluation
