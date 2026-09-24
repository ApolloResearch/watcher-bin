from http import HTTPStatus
from typing import Any, cast

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.hook_call_error import HookCallError
from ...models.http_validation_error import HTTPValidationError
from ...models.pre_tool_use_hook_request import PreToolUseHookRequest
from ...models.pre_tool_use_hook_response import PreToolUseHookResponse
from ...types import Response


def _get_kwargs(
    *,
    body: PreToolUseHookRequest,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/v1/hooks/pre-tool-use",
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> (
    Any
    | HTTPValidationError
    | list[HookCallError | PreToolUseHookResponse]
    | PreToolUseHookResponse
    | None
):
    if response.status_code == 200:

        def _parse_response_200(
            data: object,
        ) -> list[HookCallError | PreToolUseHookResponse] | PreToolUseHookResponse:
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                response_200_type_0 = PreToolUseHookResponse.from_dict(data)

                return response_200_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            if not isinstance(data, list):
                raise TypeError()
            response_200_type_1 = []
            _response_200_type_1 = data
            for response_200_type_1_item_data in _response_200_type_1:

                def _parse_response_200_type_1_item(
                    data: object,
                ) -> HookCallError | PreToolUseHookResponse:
                    try:
                        if not isinstance(data, dict):
                            raise TypeError()
                        response_200_type_1_item_type_0 = (
                            PreToolUseHookResponse.from_dict(data)
                        )

                        return response_200_type_1_item_type_0
                    except (TypeError, ValueError, AttributeError, KeyError):
                        pass
                    if not isinstance(data, dict):
                        raise TypeError()
                    response_200_type_1_item_type_1 = HookCallError.from_dict(data)

                    return response_200_type_1_item_type_1

                response_200_type_1_item = _parse_response_200_type_1_item(
                    response_200_type_1_item_data
                )

                response_200_type_1.append(response_200_type_1_item)

            return response_200_type_1

        response_200 = _parse_response_200(response.json())

        return response_200

    if response.status_code == 413:
        response_413 = cast(Any, None)
        return response_413

    if response.status_code == 422:
        response_422 = HTTPValidationError.from_dict(response.json())

        return response_422

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Response[
    Any
    | HTTPValidationError
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
    body: PreToolUseHookRequest,
) -> Response[
    Any
    | HTTPValidationError
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

    `settings_overrides` accepts YAML text or a JSON object and uses the normal
    administrator permission rules. Locked settings reject any override with
    HTTP 422. The effective `enforcement.mode` selects enforcement, observation,
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

    Args:
        body (PreToolUseHookRequest): Evaluate pending tool calls or ingest a transcript through
            the generic hook.

            Send the conversation once in `messages` and select pending calls with
            `input`. A scalar input returns one response; a list returns one outcome
            per input in the same order, including each input's `tool_use_id`. Null,
            omitted, or empty-list input ingests the transcript without grading or
            writing decisions and returns an empty list, regardless of enforcement mode.
            Named observe calls return completed judgments with a deferred applied
            decision. Enforce and observe support ephemeral evaluation and evaluation
            without session-write permission; recording requires that permission.
            All calls share one transcript, which is ingested once when recording is enabled.

            Input lists accept at most 32 items, including blank or ephemeral inputs.
            Larger lists are rejected with HTTP 422 before ingestion or grading.
            Batches with multiple inputs require top-level `messages`. Their inputs
            must omit `messages` or supply null or an empty list, so the transcript is
            sent only once. Scalars and single-item lists may supply `input.messages`;
            if both locations are non-null, their transcripts must match. An input
            with an explicitly blank tool name only ingests and retains its response shape.
            Paused and unnamed inputs need no grading admission;
            authorized ingestion still uses normal database resources.

            Send structured `messages`, including the assistant message containing each
            pending call. Pre-rendered `transcript` and caller `triage_assessment` are
            rejected. A recorded named call requires `input.tool_use_id` matching one
            call in those messages; different batch inputs must name different ids.
            The selected tool name and arguments must match every transcript occurrence
            of its ID. Argument object key order is ignored; JSON value types and string
            content must agree. Omitted `tool_input` matches an empty arguments object;
            explicit null does not. Mismatches return HTTP 422 before grading or ingestion.
            `ephemeral` suppresses transcript, decision, and grade persistence, but not
            usage. Enforce and observe requests may both use it.

            `external_ids` includes each distinct conversation ID from the harness
            and gateway, including a separate gateway-issued ID when available.
            A null value explicitly opts into transcript-prefix
            reconciliation and still names the harness. Recorded requests require this
            mapping. `user` supplies the developer email only when the authenticated
            caller can impersonate; otherwise attribution stays with that caller.

            `settings_overrides` accepts a YAML string or JSON object that the server
            will merge onto administrator settings as a local settings layer.
            Administrator locks reject overrides with HTTP 422, even when they repeat
            a locked value. Set `enforcement.mode` there for observe or paused behavior;
            omitted overrides inherit the administrator's settings. A gateway's
            server-owned capability limit independently prevents unsupported enforcement.

            `mode=triage_only` bounds grading depth: triage can allow but cannot deny;
            otherwise it escalates without running the gateway monitor. `skip_rules`
            is for clients that already evaluated deterministic stages. When they send
            `policy_version` (`<version>@<builtin digest>`), a stale token forces those
            stages to run again against the server's current policy.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError | list[HookCallError | PreToolUseHookResponse] | PreToolUseHookResponse]
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
    body: PreToolUseHookRequest,
) -> (
    Any
    | HTTPValidationError
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

    `settings_overrides` accepts YAML text or a JSON object and uses the normal
    administrator permission rules. Locked settings reject any override with
    HTTP 422. The effective `enforcement.mode` selects enforcement, observation,
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

    Args:
        body (PreToolUseHookRequest): Evaluate pending tool calls or ingest a transcript through
            the generic hook.

            Send the conversation once in `messages` and select pending calls with
            `input`. A scalar input returns one response; a list returns one outcome
            per input in the same order, including each input's `tool_use_id`. Null,
            omitted, or empty-list input ingests the transcript without grading or
            writing decisions and returns an empty list, regardless of enforcement mode.
            Named observe calls return completed judgments with a deferred applied
            decision. Enforce and observe support ephemeral evaluation and evaluation
            without session-write permission; recording requires that permission.
            All calls share one transcript, which is ingested once when recording is enabled.

            Input lists accept at most 32 items, including blank or ephemeral inputs.
            Larger lists are rejected with HTTP 422 before ingestion or grading.
            Batches with multiple inputs require top-level `messages`. Their inputs
            must omit `messages` or supply null or an empty list, so the transcript is
            sent only once. Scalars and single-item lists may supply `input.messages`;
            if both locations are non-null, their transcripts must match. An input
            with an explicitly blank tool name only ingests and retains its response shape.
            Paused and unnamed inputs need no grading admission;
            authorized ingestion still uses normal database resources.

            Send structured `messages`, including the assistant message containing each
            pending call. Pre-rendered `transcript` and caller `triage_assessment` are
            rejected. A recorded named call requires `input.tool_use_id` matching one
            call in those messages; different batch inputs must name different ids.
            The selected tool name and arguments must match every transcript occurrence
            of its ID. Argument object key order is ignored; JSON value types and string
            content must agree. Omitted `tool_input` matches an empty arguments object;
            explicit null does not. Mismatches return HTTP 422 before grading or ingestion.
            `ephemeral` suppresses transcript, decision, and grade persistence, but not
            usage. Enforce and observe requests may both use it.

            `external_ids` includes each distinct conversation ID from the harness
            and gateway, including a separate gateway-issued ID when available.
            A null value explicitly opts into transcript-prefix
            reconciliation and still names the harness. Recorded requests require this
            mapping. `user` supplies the developer email only when the authenticated
            caller can impersonate; otherwise attribution stays with that caller.

            `settings_overrides` accepts a YAML string or JSON object that the server
            will merge onto administrator settings as a local settings layer.
            Administrator locks reject overrides with HTTP 422, even when they repeat
            a locked value. Set `enforcement.mode` there for observe or paused behavior;
            omitted overrides inherit the administrator's settings. A gateway's
            server-owned capability limit independently prevents unsupported enforcement.

            `mode=triage_only` bounds grading depth: triage can allow but cannot deny;
            otherwise it escalates without running the gateway monitor. `skip_rules`
            is for clients that already evaluated deterministic stages. When they send
            `policy_version` (`<version>@<builtin digest>`), a stale token forces those
            stages to run again against the server's current policy.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError | list[HookCallError | PreToolUseHookResponse] | PreToolUseHookResponse
    """

    return sync_detailed(
        client=client,
        body=body,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient | Client,
    body: PreToolUseHookRequest,
) -> Response[
    Any
    | HTTPValidationError
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

    `settings_overrides` accepts YAML text or a JSON object and uses the normal
    administrator permission rules. Locked settings reject any override with
    HTTP 422. The effective `enforcement.mode` selects enforcement, observation,
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

    Args:
        body (PreToolUseHookRequest): Evaluate pending tool calls or ingest a transcript through
            the generic hook.

            Send the conversation once in `messages` and select pending calls with
            `input`. A scalar input returns one response; a list returns one outcome
            per input in the same order, including each input's `tool_use_id`. Null,
            omitted, or empty-list input ingests the transcript without grading or
            writing decisions and returns an empty list, regardless of enforcement mode.
            Named observe calls return completed judgments with a deferred applied
            decision. Enforce and observe support ephemeral evaluation and evaluation
            without session-write permission; recording requires that permission.
            All calls share one transcript, which is ingested once when recording is enabled.

            Input lists accept at most 32 items, including blank or ephemeral inputs.
            Larger lists are rejected with HTTP 422 before ingestion or grading.
            Batches with multiple inputs require top-level `messages`. Their inputs
            must omit `messages` or supply null or an empty list, so the transcript is
            sent only once. Scalars and single-item lists may supply `input.messages`;
            if both locations are non-null, their transcripts must match. An input
            with an explicitly blank tool name only ingests and retains its response shape.
            Paused and unnamed inputs need no grading admission;
            authorized ingestion still uses normal database resources.

            Send structured `messages`, including the assistant message containing each
            pending call. Pre-rendered `transcript` and caller `triage_assessment` are
            rejected. A recorded named call requires `input.tool_use_id` matching one
            call in those messages; different batch inputs must name different ids.
            The selected tool name and arguments must match every transcript occurrence
            of its ID. Argument object key order is ignored; JSON value types and string
            content must agree. Omitted `tool_input` matches an empty arguments object;
            explicit null does not. Mismatches return HTTP 422 before grading or ingestion.
            `ephemeral` suppresses transcript, decision, and grade persistence, but not
            usage. Enforce and observe requests may both use it.

            `external_ids` includes each distinct conversation ID from the harness
            and gateway, including a separate gateway-issued ID when available.
            A null value explicitly opts into transcript-prefix
            reconciliation and still names the harness. Recorded requests require this
            mapping. `user` supplies the developer email only when the authenticated
            caller can impersonate; otherwise attribution stays with that caller.

            `settings_overrides` accepts a YAML string or JSON object that the server
            will merge onto administrator settings as a local settings layer.
            Administrator locks reject overrides with HTTP 422, even when they repeat
            a locked value. Set `enforcement.mode` there for observe or paused behavior;
            omitted overrides inherit the administrator's settings. A gateway's
            server-owned capability limit independently prevents unsupported enforcement.

            `mode=triage_only` bounds grading depth: triage can allow but cannot deny;
            otherwise it escalates without running the gateway monitor. `skip_rules`
            is for clients that already evaluated deterministic stages. When they send
            `policy_version` (`<version>@<builtin digest>`), a stale token forces those
            stages to run again against the server's current policy.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError | list[HookCallError | PreToolUseHookResponse] | PreToolUseHookResponse]
    """

    kwargs = _get_kwargs(
        body=body,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient | Client,
    body: PreToolUseHookRequest,
) -> (
    Any
    | HTTPValidationError
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

    `settings_overrides` accepts YAML text or a JSON object and uses the normal
    administrator permission rules. Locked settings reject any override with
    HTTP 422. The effective `enforcement.mode` selects enforcement, observation,
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

    Args:
        body (PreToolUseHookRequest): Evaluate pending tool calls or ingest a transcript through
            the generic hook.

            Send the conversation once in `messages` and select pending calls with
            `input`. A scalar input returns one response; a list returns one outcome
            per input in the same order, including each input's `tool_use_id`. Null,
            omitted, or empty-list input ingests the transcript without grading or
            writing decisions and returns an empty list, regardless of enforcement mode.
            Named observe calls return completed judgments with a deferred applied
            decision. Enforce and observe support ephemeral evaluation and evaluation
            without session-write permission; recording requires that permission.
            All calls share one transcript, which is ingested once when recording is enabled.

            Input lists accept at most 32 items, including blank or ephemeral inputs.
            Larger lists are rejected with HTTP 422 before ingestion or grading.
            Batches with multiple inputs require top-level `messages`. Their inputs
            must omit `messages` or supply null or an empty list, so the transcript is
            sent only once. Scalars and single-item lists may supply `input.messages`;
            if both locations are non-null, their transcripts must match. An input
            with an explicitly blank tool name only ingests and retains its response shape.
            Paused and unnamed inputs need no grading admission;
            authorized ingestion still uses normal database resources.

            Send structured `messages`, including the assistant message containing each
            pending call. Pre-rendered `transcript` and caller `triage_assessment` are
            rejected. A recorded named call requires `input.tool_use_id` matching one
            call in those messages; different batch inputs must name different ids.
            The selected tool name and arguments must match every transcript occurrence
            of its ID. Argument object key order is ignored; JSON value types and string
            content must agree. Omitted `tool_input` matches an empty arguments object;
            explicit null does not. Mismatches return HTTP 422 before grading or ingestion.
            `ephemeral` suppresses transcript, decision, and grade persistence, but not
            usage. Enforce and observe requests may both use it.

            `external_ids` includes each distinct conversation ID from the harness
            and gateway, including a separate gateway-issued ID when available.
            A null value explicitly opts into transcript-prefix
            reconciliation and still names the harness. Recorded requests require this
            mapping. `user` supplies the developer email only when the authenticated
            caller can impersonate; otherwise attribution stays with that caller.

            `settings_overrides` accepts a YAML string or JSON object that the server
            will merge onto administrator settings as a local settings layer.
            Administrator locks reject overrides with HTTP 422, even when they repeat
            a locked value. Set `enforcement.mode` there for observe or paused behavior;
            omitted overrides inherit the administrator's settings. A gateway's
            server-owned capability limit independently prevents unsupported enforcement.

            `mode=triage_only` bounds grading depth: triage can allow but cannot deny;
            otherwise it escalates without running the gateway monitor. `skip_rules`
            is for clients that already evaluated deterministic stages. When they send
            `policy_version` (`<version>@<builtin digest>`), a stale token forces those
            stages to run again against the server's current policy.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError | list[HookCallError | PreToolUseHookResponse] | PreToolUseHookResponse
    """

    return (
        await asyncio_detailed(
            client=client,
            body=body,
        )
    ).parsed
