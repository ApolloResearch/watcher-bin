from http import HTTPStatus
from typing import Any, cast

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.claude_code_hook_request import ClaudeCodeHookRequest
from ...models.codex_hook_request import CodexHookRequest
from ...models.copilot_hook_request import CopilotHookRequest
from ...models.hook_append_response import HookAppendResponse
from ...models.hook_call_error import HookCallError
from ...models.http_validation_error import HTTPValidationError
from ...models.pre_tool_use_hook_request import PreToolUseHookRequest
from ...models.pre_tool_use_hook_response import PreToolUseHookResponse
from ...models.raw_pre_tool_use_hook_request import RawPreToolUseHookRequest
from ...types import Response


def _get_kwargs(
    *,
    body: ClaudeCodeHookRequest
    | CodexHookRequest
    | CopilotHookRequest
    | PreToolUseHookRequest
    | RawPreToolUseHookRequest,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/v1/hooks/pre-tool-use",
    }

    if (
        isinstance(body, PreToolUseHookRequest)
        or isinstance(body, ClaudeCodeHookRequest)
        or isinstance(body, CodexHookRequest)
        or isinstance(body, CopilotHookRequest)
    ):
        _kwargs["json"] = body.to_dict()
    else:
        _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> (
    Any
    | HTTPValidationError
    | HookAppendResponse
    | list[HookCallError | PreToolUseHookResponse]
    | PreToolUseHookResponse
    | None
):
    if response.status_code == 200:

        def _parse_response_200(
            data: object,
        ) -> (
            HookAppendResponse
            | list[HookCallError | PreToolUseHookResponse]
            | PreToolUseHookResponse
        ):
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                response_200_type_0 = HookAppendResponse.from_dict(data)

                return response_200_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                response_200_type_1 = PreToolUseHookResponse.from_dict(data)

                return response_200_type_1
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            if not isinstance(data, list):
                raise TypeError()
            response_200_type_2 = []
            _response_200_type_2 = data
            for response_200_type_2_item_data in _response_200_type_2:

                def _parse_response_200_type_2_item(
                    data: object,
                ) -> HookCallError | PreToolUseHookResponse:
                    try:
                        if not isinstance(data, dict):
                            raise TypeError()
                        response_200_type_2_item_type_0 = (
                            PreToolUseHookResponse.from_dict(data)
                        )

                        return response_200_type_2_item_type_0
                    except (TypeError, ValueError, AttributeError, KeyError):
                        pass
                    if not isinstance(data, dict):
                        raise TypeError()
                    response_200_type_2_item_type_1 = HookCallError.from_dict(data)

                    return response_200_type_2_item_type_1

                response_200_type_2_item = _parse_response_200_type_2_item(
                    response_200_type_2_item_data
                )

                response_200_type_2.append(response_200_type_2_item)

            return response_200_type_2

        response_200 = _parse_response_200(response.json())

        return response_200

    if response.status_code == 404:
        response_404 = cast(Any, None)
        return response_404

    if response.status_code == 409:
        response_409 = cast(Any, None)
        return response_409

    if response.status_code == 413:
        response_413 = cast(Any, None)
        return response_413

    if response.status_code == 422:
        response_422 = HTTPValidationError.from_dict(response.json())

        return response_422

    if response.status_code == 503:
        response_503 = cast(Any, None)
        return response_503

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Response[
    Any
    | HTTPValidationError
    | HookAppendResponse
    | list[HookCallError | PreToolUseHookResponse]
    | PreToolUseHookResponse
]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient | Client,
    body: ClaudeCodeHookRequest
    | CodexHookRequest
    | CopilotHookRequest
    | PreToolUseHookRequest
    | RawPreToolUseHookRequest,
) -> Response[
    Any
    | HTTPValidationError
    | HookAppendResponse
    | list[HookCallError | PreToolUseHookResponse]
    | PreToolUseHookResponse
]:
    """Pre Tool Use Hook

     Evaluate one or several pending calls, or accept a transcript with no pending call.

    Scalar input returns one decision or an HTTP refusal. A batch returns an
    ordered result per input; a refused input carries status_code/detail while
    other inputs continue. Null or empty input returns an empty list and only
    ingests the top-level `messages`. All inputs share one transcript, recorded
    once along with successful judgments.
    Decisions attach to each input's `tool_use_id`. For evaluated requests,
    `ephemeral` skips transcript, decision, and grade persistence while retaining
    usage accounting. Enforce and observe both return completed judgments,
    including when ephemeral or the caller cannot record sessions.

    An append cannot be ephemeral and requires authority to write its parent
    session. It returns a HookAppendResponse containing the committed next
    anchor and an ordered results list, even for scalar or transcript-only
    input. Messages and available decisions are stored before success; reuse
    the returned anchor directly for the next append. Recording failure is
    HTTP 503 and can follow committed messages. Its body retains ordered
    `results`, including denies, without an `append_after` cursor. Apply those
    decisions and retry the same append to finish recording.

    `settings_overrides` accepts YAML text or a JSON object and uses the normal
    administrator permission rules. An override that changes a locked setting
    is refused with HTTP 422; one that repeats it is accepted. The effective `enforcement.mode` selects
    enforcement, observation,
    or ingestion only. Observe returns the completed judgment with a deferred
    applied decision. Paused and unnamed calls do not evaluate; authorized
    callers still record the transcript. HTTP 422 errors use a list of detail
    entries, including validation and settings overrides.

    The caller enforces returned decisions; this endpoint does not execute or
    block tools itself. Deterministic stages precede triage and gateway grading.
    `mode=triage_only` bounds grading depth, while `skip_rules` and
    `policy_version` support clients that already evaluated deterministic stages.
    Stage waits are bounded in both enforce and observe, but detached grades
    can finish and count usage after a timeout or disconnect.
    Callers own transport-failure handling.

    Completed evaluations are reused per org, session and tool-use ID when the
    stored name and JSON arguments match. Current enforcement posture is applied
    to the original judgment; policy or grading-depth changes do not invalidate
    it. `force_regrade=true` evaluates again and permits replacing the recorded
    decision, including with an observation. Failed and unjudged evaluations
    retry normally. Reuse requires known external IDs, ingestion authority and
    permission to read the resolved session; id-less, ephemeral and write-only
    callers evaluate normally, as do unknown stored call metadata shapes.
    Reuse creates no new grades, usage or alerts, though the transcript still
    ingests. Concurrent misses and retries before post-response recording may
    evaluate more than once. Paused mode never evaluates, even when forced.

    With `format="raw"`, send a provider request (`request_body`) and its
    complete response (`response_body`) in one supported wire format (OpenAI
    Chat Completions or Responses, Anthropic Messages, Gemini generateContent
    or Bedrock Converse) plus the client-facing endpoint path in `url`, instead
    of `messages` and `input`. Watcher converts the pair and evaluates the
    selected new client calls. The response is a list, one output per selected
    call in response order; each `tool_use_id` is the provider's call ID.
    Gemini calls get generated IDs and are matched by order within the selected
    candidate. `response_index` selects by zero-based array position and is
    required when there are multiple alternatives. Deliver only the selected
    choice or candidate. Match every
    executable client call to exactly one output before applying its decision.
    Withhold the response if a call has no output, IDs are duplicated, or an
    output cannot be matched to a call. For Gemini, require equal call and output
    counts. An error output is not permission to execute a call.

    Anthropic calls before the final `fallback` block have no output. An empty
    list means no client calls were selected, not that the original response
    contains none. There is no limit on the number of tool calls in one response.
    Known coding harnesses are recognized from the request and `user_agent` and
    contribute their session IDs. Their own helper requests without selected
    client calls (Claude Code background requests, Codex thread titles,
    approval reviews and memory extraction, Antigravity titles) return `[]`
    and are not recorded. The gateway still checks those responses for
    executable calls.

    Args:
        body (ClaudeCodeHookRequest | CodexHookRequest | CopilotHookRequest |
            PreToolUseHookRequest | RawPreToolUseHookRequest):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError | HookAppendResponse | list[HookCallError | PreToolUseHookResponse] | PreToolUseHookResponse]
    """

    kwargs = _get_kwargs(
        body=body,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient | Client,
    body: ClaudeCodeHookRequest
    | CodexHookRequest
    | CopilotHookRequest
    | PreToolUseHookRequest
    | RawPreToolUseHookRequest,
) -> (
    Any
    | HTTPValidationError
    | HookAppendResponse
    | list[HookCallError | PreToolUseHookResponse]
    | PreToolUseHookResponse
    | None
):
    """Pre Tool Use Hook

     Evaluate one or several pending calls, or accept a transcript with no pending call.

    Scalar input returns one decision or an HTTP refusal. A batch returns an
    ordered result per input; a refused input carries status_code/detail while
    other inputs continue. Null or empty input returns an empty list and only
    ingests the top-level `messages`. All inputs share one transcript, recorded
    once along with successful judgments.
    Decisions attach to each input's `tool_use_id`. For evaluated requests,
    `ephemeral` skips transcript, decision, and grade persistence while retaining
    usage accounting. Enforce and observe both return completed judgments,
    including when ephemeral or the caller cannot record sessions.

    An append cannot be ephemeral and requires authority to write its parent
    session. It returns a HookAppendResponse containing the committed next
    anchor and an ordered results list, even for scalar or transcript-only
    input. Messages and available decisions are stored before success; reuse
    the returned anchor directly for the next append. Recording failure is
    HTTP 503 and can follow committed messages. Its body retains ordered
    `results`, including denies, without an `append_after` cursor. Apply those
    decisions and retry the same append to finish recording.

    `settings_overrides` accepts YAML text or a JSON object and uses the normal
    administrator permission rules. An override that changes a locked setting
    is refused with HTTP 422; one that repeats it is accepted. The effective `enforcement.mode` selects
    enforcement, observation,
    or ingestion only. Observe returns the completed judgment with a deferred
    applied decision. Paused and unnamed calls do not evaluate; authorized
    callers still record the transcript. HTTP 422 errors use a list of detail
    entries, including validation and settings overrides.

    The caller enforces returned decisions; this endpoint does not execute or
    block tools itself. Deterministic stages precede triage and gateway grading.
    `mode=triage_only` bounds grading depth, while `skip_rules` and
    `policy_version` support clients that already evaluated deterministic stages.
    Stage waits are bounded in both enforce and observe, but detached grades
    can finish and count usage after a timeout or disconnect.
    Callers own transport-failure handling.

    Completed evaluations are reused per org, session and tool-use ID when the
    stored name and JSON arguments match. Current enforcement posture is applied
    to the original judgment; policy or grading-depth changes do not invalidate
    it. `force_regrade=true` evaluates again and permits replacing the recorded
    decision, including with an observation. Failed and unjudged evaluations
    retry normally. Reuse requires known external IDs, ingestion authority and
    permission to read the resolved session; id-less, ephemeral and write-only
    callers evaluate normally, as do unknown stored call metadata shapes.
    Reuse creates no new grades, usage or alerts, though the transcript still
    ingests. Concurrent misses and retries before post-response recording may
    evaluate more than once. Paused mode never evaluates, even when forced.

    With `format="raw"`, send a provider request (`request_body`) and its
    complete response (`response_body`) in one supported wire format (OpenAI
    Chat Completions or Responses, Anthropic Messages, Gemini generateContent
    or Bedrock Converse) plus the client-facing endpoint path in `url`, instead
    of `messages` and `input`. Watcher converts the pair and evaluates the
    selected new client calls. The response is a list, one output per selected
    call in response order; each `tool_use_id` is the provider's call ID.
    Gemini calls get generated IDs and are matched by order within the selected
    candidate. `response_index` selects by zero-based array position and is
    required when there are multiple alternatives. Deliver only the selected
    choice or candidate. Match every
    executable client call to exactly one output before applying its decision.
    Withhold the response if a call has no output, IDs are duplicated, or an
    output cannot be matched to a call. For Gemini, require equal call and output
    counts. An error output is not permission to execute a call.

    Anthropic calls before the final `fallback` block have no output. An empty
    list means no client calls were selected, not that the original response
    contains none. There is no limit on the number of tool calls in one response.
    Known coding harnesses are recognized from the request and `user_agent` and
    contribute their session IDs. Their own helper requests without selected
    client calls (Claude Code background requests, Codex thread titles,
    approval reviews and memory extraction, Antigravity titles) return `[]`
    and are not recorded. The gateway still checks those responses for
    executable calls.

    Args:
        body (ClaudeCodeHookRequest | CodexHookRequest | CopilotHookRequest |
            PreToolUseHookRequest | RawPreToolUseHookRequest):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError | HookAppendResponse | list[HookCallError | PreToolUseHookResponse] | PreToolUseHookResponse
    """

    return sync_detailed(
        client=client,
        body=body,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient | Client,
    body: ClaudeCodeHookRequest
    | CodexHookRequest
    | CopilotHookRequest
    | PreToolUseHookRequest
    | RawPreToolUseHookRequest,
) -> Response[
    Any
    | HTTPValidationError
    | HookAppendResponse
    | list[HookCallError | PreToolUseHookResponse]
    | PreToolUseHookResponse
]:
    """Pre Tool Use Hook

     Evaluate one or several pending calls, or accept a transcript with no pending call.

    Scalar input returns one decision or an HTTP refusal. A batch returns an
    ordered result per input; a refused input carries status_code/detail while
    other inputs continue. Null or empty input returns an empty list and only
    ingests the top-level `messages`. All inputs share one transcript, recorded
    once along with successful judgments.
    Decisions attach to each input's `tool_use_id`. For evaluated requests,
    `ephemeral` skips transcript, decision, and grade persistence while retaining
    usage accounting. Enforce and observe both return completed judgments,
    including when ephemeral or the caller cannot record sessions.

    An append cannot be ephemeral and requires authority to write its parent
    session. It returns a HookAppendResponse containing the committed next
    anchor and an ordered results list, even for scalar or transcript-only
    input. Messages and available decisions are stored before success; reuse
    the returned anchor directly for the next append. Recording failure is
    HTTP 503 and can follow committed messages. Its body retains ordered
    `results`, including denies, without an `append_after` cursor. Apply those
    decisions and retry the same append to finish recording.

    `settings_overrides` accepts YAML text or a JSON object and uses the normal
    administrator permission rules. An override that changes a locked setting
    is refused with HTTP 422; one that repeats it is accepted. The effective `enforcement.mode` selects
    enforcement, observation,
    or ingestion only. Observe returns the completed judgment with a deferred
    applied decision. Paused and unnamed calls do not evaluate; authorized
    callers still record the transcript. HTTP 422 errors use a list of detail
    entries, including validation and settings overrides.

    The caller enforces returned decisions; this endpoint does not execute or
    block tools itself. Deterministic stages precede triage and gateway grading.
    `mode=triage_only` bounds grading depth, while `skip_rules` and
    `policy_version` support clients that already evaluated deterministic stages.
    Stage waits are bounded in both enforce and observe, but detached grades
    can finish and count usage after a timeout or disconnect.
    Callers own transport-failure handling.

    Completed evaluations are reused per org, session and tool-use ID when the
    stored name and JSON arguments match. Current enforcement posture is applied
    to the original judgment; policy or grading-depth changes do not invalidate
    it. `force_regrade=true` evaluates again and permits replacing the recorded
    decision, including with an observation. Failed and unjudged evaluations
    retry normally. Reuse requires known external IDs, ingestion authority and
    permission to read the resolved session; id-less, ephemeral and write-only
    callers evaluate normally, as do unknown stored call metadata shapes.
    Reuse creates no new grades, usage or alerts, though the transcript still
    ingests. Concurrent misses and retries before post-response recording may
    evaluate more than once. Paused mode never evaluates, even when forced.

    With `format="raw"`, send a provider request (`request_body`) and its
    complete response (`response_body`) in one supported wire format (OpenAI
    Chat Completions or Responses, Anthropic Messages, Gemini generateContent
    or Bedrock Converse) plus the client-facing endpoint path in `url`, instead
    of `messages` and `input`. Watcher converts the pair and evaluates the
    selected new client calls. The response is a list, one output per selected
    call in response order; each `tool_use_id` is the provider's call ID.
    Gemini calls get generated IDs and are matched by order within the selected
    candidate. `response_index` selects by zero-based array position and is
    required when there are multiple alternatives. Deliver only the selected
    choice or candidate. Match every
    executable client call to exactly one output before applying its decision.
    Withhold the response if a call has no output, IDs are duplicated, or an
    output cannot be matched to a call. For Gemini, require equal call and output
    counts. An error output is not permission to execute a call.

    Anthropic calls before the final `fallback` block have no output. An empty
    list means no client calls were selected, not that the original response
    contains none. There is no limit on the number of tool calls in one response.
    Known coding harnesses are recognized from the request and `user_agent` and
    contribute their session IDs. Their own helper requests without selected
    client calls (Claude Code background requests, Codex thread titles,
    approval reviews and memory extraction, Antigravity titles) return `[]`
    and are not recorded. The gateway still checks those responses for
    executable calls.

    Args:
        body (ClaudeCodeHookRequest | CodexHookRequest | CopilotHookRequest |
            PreToolUseHookRequest | RawPreToolUseHookRequest):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError | HookAppendResponse | list[HookCallError | PreToolUseHookResponse] | PreToolUseHookResponse]
    """

    kwargs = _get_kwargs(
        body=body,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient | Client,
    body: ClaudeCodeHookRequest
    | CodexHookRequest
    | CopilotHookRequest
    | PreToolUseHookRequest
    | RawPreToolUseHookRequest,
) -> (
    Any
    | HTTPValidationError
    | HookAppendResponse
    | list[HookCallError | PreToolUseHookResponse]
    | PreToolUseHookResponse
    | None
):
    """Pre Tool Use Hook

     Evaluate one or several pending calls, or accept a transcript with no pending call.

    Scalar input returns one decision or an HTTP refusal. A batch returns an
    ordered result per input; a refused input carries status_code/detail while
    other inputs continue. Null or empty input returns an empty list and only
    ingests the top-level `messages`. All inputs share one transcript, recorded
    once along with successful judgments.
    Decisions attach to each input's `tool_use_id`. For evaluated requests,
    `ephemeral` skips transcript, decision, and grade persistence while retaining
    usage accounting. Enforce and observe both return completed judgments,
    including when ephemeral or the caller cannot record sessions.

    An append cannot be ephemeral and requires authority to write its parent
    session. It returns a HookAppendResponse containing the committed next
    anchor and an ordered results list, even for scalar or transcript-only
    input. Messages and available decisions are stored before success; reuse
    the returned anchor directly for the next append. Recording failure is
    HTTP 503 and can follow committed messages. Its body retains ordered
    `results`, including denies, without an `append_after` cursor. Apply those
    decisions and retry the same append to finish recording.

    `settings_overrides` accepts YAML text or a JSON object and uses the normal
    administrator permission rules. An override that changes a locked setting
    is refused with HTTP 422; one that repeats it is accepted. The effective `enforcement.mode` selects
    enforcement, observation,
    or ingestion only. Observe returns the completed judgment with a deferred
    applied decision. Paused and unnamed calls do not evaluate; authorized
    callers still record the transcript. HTTP 422 errors use a list of detail
    entries, including validation and settings overrides.

    The caller enforces returned decisions; this endpoint does not execute or
    block tools itself. Deterministic stages precede triage and gateway grading.
    `mode=triage_only` bounds grading depth, while `skip_rules` and
    `policy_version` support clients that already evaluated deterministic stages.
    Stage waits are bounded in both enforce and observe, but detached grades
    can finish and count usage after a timeout or disconnect.
    Callers own transport-failure handling.

    Completed evaluations are reused per org, session and tool-use ID when the
    stored name and JSON arguments match. Current enforcement posture is applied
    to the original judgment; policy or grading-depth changes do not invalidate
    it. `force_regrade=true` evaluates again and permits replacing the recorded
    decision, including with an observation. Failed and unjudged evaluations
    retry normally. Reuse requires known external IDs, ingestion authority and
    permission to read the resolved session; id-less, ephemeral and write-only
    callers evaluate normally, as do unknown stored call metadata shapes.
    Reuse creates no new grades, usage or alerts, though the transcript still
    ingests. Concurrent misses and retries before post-response recording may
    evaluate more than once. Paused mode never evaluates, even when forced.

    With `format="raw"`, send a provider request (`request_body`) and its
    complete response (`response_body`) in one supported wire format (OpenAI
    Chat Completions or Responses, Anthropic Messages, Gemini generateContent
    or Bedrock Converse) plus the client-facing endpoint path in `url`, instead
    of `messages` and `input`. Watcher converts the pair and evaluates the
    selected new client calls. The response is a list, one output per selected
    call in response order; each `tool_use_id` is the provider's call ID.
    Gemini calls get generated IDs and are matched by order within the selected
    candidate. `response_index` selects by zero-based array position and is
    required when there are multiple alternatives. Deliver only the selected
    choice or candidate. Match every
    executable client call to exactly one output before applying its decision.
    Withhold the response if a call has no output, IDs are duplicated, or an
    output cannot be matched to a call. For Gemini, require equal call and output
    counts. An error output is not permission to execute a call.

    Anthropic calls before the final `fallback` block have no output. An empty
    list means no client calls were selected, not that the original response
    contains none. There is no limit on the number of tool calls in one response.
    Known coding harnesses are recognized from the request and `user_agent` and
    contribute their session IDs. Their own helper requests without selected
    client calls (Claude Code background requests, Codex thread titles,
    approval reviews and memory extraction, Antigravity titles) return `[]`
    and are not recorded. The gateway still checks those responses for
    executable calls.

    Args:
        body (ClaudeCodeHookRequest | CodexHookRequest | CopilotHookRequest |
            PreToolUseHookRequest | RawPreToolUseHookRequest):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError | HookAppendResponse | list[HookCallError | PreToolUseHookResponse] | PreToolUseHookResponse
    """

    return (
        await asyncio_detailed(
            client=client,
            body=body,
        )
    ).parsed
