from http import HTTPStatus
from typing import Any, cast

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.grade_request import GradeRequest
from ...models.grade_response import GradeResponse
from ...models.http_validation_error import HTTPValidationError
from ...types import Response


def _get_kwargs(
    *,
    body: GradeRequest,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/v1/grade",
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Any | GradeResponse | HTTPValidationError | None:
    if response.status_code == 200:
        response_200 = GradeResponse.from_dict(response.json())

        return response_200

    if response.status_code == 422:
        response_422 = HTTPValidationError.from_dict(response.json())

        return response_422

    if response.status_code == 499:
        response_499 = cast(Any, None)
        return response_499

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Response[Any | GradeResponse | HTTPValidationError]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient | Client,
    body: GradeRequest,
) -> Response[Any | GradeResponse | HTTPValidationError]:
    """Grade

     Grade trajectories with explicitly named graders.

    DB-backed grading is gated by session ownership: callers may only grade
    sessions they own, unless they hold ``sessions:write:any`` (or are an
    admin / internal-token / local-mode caller).
    Flagged-grade Slack notifications fire post-response via BackgroundTasks
    only for DB-backed trajectory grading. Tool-call grading
    (``tool_call_run_kind``) persists the grade but does NOT notify here — its
    alert fires later, at decision ingest (``POST
    /v1/tool-call-decisions/batch``), once the coding agent and Analyzer link
    are known. Plain ephemeral grading never notifies.

    Args:
        body (GradeRequest): Request body for POST /v1/grade.

            Grades with graders the caller addresses explicitly by UUID (see
            ``_GradePayloadBase`` for the payload modes). ``grader_ids`` is required:
            this endpoint never chooses a grader for the caller. To run the
            server-managed monitors without holding grader UUIDs, use
            POST /v1/monitors/{role}/grade instead.

            ``tool_call_run_kind`` records an ephemeral grade as tool-call audit
            provenance. When set, each grade result includes a ``tool_call_grade_id``
            that can later be attached to a tool-call decision, and the caller may send
            ``session_id`` + ``tool_use_id`` so the grade row records which call it
            graded from birth.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | GradeResponse | HTTPValidationError]
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
    body: GradeRequest,
) -> Any | GradeResponse | HTTPValidationError | None:
    """Grade

     Grade trajectories with explicitly named graders.

    DB-backed grading is gated by session ownership: callers may only grade
    sessions they own, unless they hold ``sessions:write:any`` (or are an
    admin / internal-token / local-mode caller).
    Flagged-grade Slack notifications fire post-response via BackgroundTasks
    only for DB-backed trajectory grading. Tool-call grading
    (``tool_call_run_kind``) persists the grade but does NOT notify here — its
    alert fires later, at decision ingest (``POST
    /v1/tool-call-decisions/batch``), once the coding agent and Analyzer link
    are known. Plain ephemeral grading never notifies.

    Args:
        body (GradeRequest): Request body for POST /v1/grade.

            Grades with graders the caller addresses explicitly by UUID (see
            ``_GradePayloadBase`` for the payload modes). ``grader_ids`` is required:
            this endpoint never chooses a grader for the caller. To run the
            server-managed monitors without holding grader UUIDs, use
            POST /v1/monitors/{role}/grade instead.

            ``tool_call_run_kind`` records an ephemeral grade as tool-call audit
            provenance. When set, each grade result includes a ``tool_call_grade_id``
            that can later be attached to a tool-call decision, and the caller may send
            ``session_id`` + ``tool_use_id`` so the grade row records which call it
            graded from birth.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | GradeResponse | HTTPValidationError
    """

    return sync_detailed(
        client=client,
        body=body,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient | Client,
    body: GradeRequest,
) -> Response[Any | GradeResponse | HTTPValidationError]:
    """Grade

     Grade trajectories with explicitly named graders.

    DB-backed grading is gated by session ownership: callers may only grade
    sessions they own, unless they hold ``sessions:write:any`` (or are an
    admin / internal-token / local-mode caller).
    Flagged-grade Slack notifications fire post-response via BackgroundTasks
    only for DB-backed trajectory grading. Tool-call grading
    (``tool_call_run_kind``) persists the grade but does NOT notify here — its
    alert fires later, at decision ingest (``POST
    /v1/tool-call-decisions/batch``), once the coding agent and Analyzer link
    are known. Plain ephemeral grading never notifies.

    Args:
        body (GradeRequest): Request body for POST /v1/grade.

            Grades with graders the caller addresses explicitly by UUID (see
            ``_GradePayloadBase`` for the payload modes). ``grader_ids`` is required:
            this endpoint never chooses a grader for the caller. To run the
            server-managed monitors without holding grader UUIDs, use
            POST /v1/monitors/{role}/grade instead.

            ``tool_call_run_kind`` records an ephemeral grade as tool-call audit
            provenance. When set, each grade result includes a ``tool_call_grade_id``
            that can later be attached to a tool-call decision, and the caller may send
            ``session_id`` + ``tool_use_id`` so the grade row records which call it
            graded from birth.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | GradeResponse | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        body=body,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient | Client,
    body: GradeRequest,
) -> Any | GradeResponse | HTTPValidationError | None:
    """Grade

     Grade trajectories with explicitly named graders.

    DB-backed grading is gated by session ownership: callers may only grade
    sessions they own, unless they hold ``sessions:write:any`` (or are an
    admin / internal-token / local-mode caller).
    Flagged-grade Slack notifications fire post-response via BackgroundTasks
    only for DB-backed trajectory grading. Tool-call grading
    (``tool_call_run_kind``) persists the grade but does NOT notify here — its
    alert fires later, at decision ingest (``POST
    /v1/tool-call-decisions/batch``), once the coding agent and Analyzer link
    are known. Plain ephemeral grading never notifies.

    Args:
        body (GradeRequest): Request body for POST /v1/grade.

            Grades with graders the caller addresses explicitly by UUID (see
            ``_GradePayloadBase`` for the payload modes). ``grader_ids`` is required:
            this endpoint never chooses a grader for the caller. To run the
            server-managed monitors without holding grader UUIDs, use
            POST /v1/monitors/{role}/grade instead.

            ``tool_call_run_kind`` records an ephemeral grade as tool-call audit
            provenance. When set, each grade result includes a ``tool_call_grade_id``
            that can later be attached to a tool-call decision, and the caller may send
            ``session_id`` + ``tool_use_id`` so the grade row records which call it
            graded from birth.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | GradeResponse | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            client=client,
            body=body,
        )
    ).parsed
