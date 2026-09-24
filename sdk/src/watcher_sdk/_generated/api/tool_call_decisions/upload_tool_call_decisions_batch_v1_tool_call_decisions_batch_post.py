from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.tool_call_decision_batch_request import ToolCallDecisionBatchRequest
from ...models.tool_call_decision_batch_response import ToolCallDecisionBatchResponse
from ...types import Response


def _get_kwargs(
    *,
    body: ToolCallDecisionBatchRequest,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/v1/tool-call-decisions/batch",
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> HTTPValidationError | ToolCallDecisionBatchResponse | None:
    if response.status_code == 200:
        response_200 = ToolCallDecisionBatchResponse.from_dict(response.json())

        return response_200

    if response.status_code == 422:
        response_422 = HTTPValidationError.from_dict(response.json())

        return response_422

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Response[HTTPValidationError | ToolCallDecisionBatchResponse]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient | Client,
    body: ToolCallDecisionBatchRequest,
) -> Response[HTTPValidationError | ToolCallDecisionBatchResponse]:
    """Upload Tool Call Decisions Batch

     Persist decisions for already-ingested tool calls, alerting on newly flagged ones.

    This endpoint is intentionally batch-oriented and post-ingest-only. The
    transcript must already exist in Watcher so each decision can be resolved to
    a canonical session message. Decisions that cannot be resolved to an
    ingested tool call, or that reference missing/already-linked grade IDs, are
    reported in the response and skipped. Other valid decisions in the same
    batch are still persisted.

    Slack alerts for flagged tool calls fire from here (not from grading): only
    once the decision is uploaded are the coding agent (from the session) and the
    Analyzer deep link available. Alerts fire once per decision — only for
    decisions newly inserted by this call, so re-pushes (e.g. pending ->
    resolved) do not re-notify.

    Args:
        body (ToolCallDecisionBatchRequest): Batch upload tool-call decisions after transcript
            ingest.

            Every decision should refer to a tool-use block already present in the
            session's messages. Valid decisions are persisted even when other items in
            the same batch cannot be resolved.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | ToolCallDecisionBatchResponse]
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
    body: ToolCallDecisionBatchRequest,
) -> HTTPValidationError | ToolCallDecisionBatchResponse | None:
    """Upload Tool Call Decisions Batch

     Persist decisions for already-ingested tool calls, alerting on newly flagged ones.

    This endpoint is intentionally batch-oriented and post-ingest-only. The
    transcript must already exist in Watcher so each decision can be resolved to
    a canonical session message. Decisions that cannot be resolved to an
    ingested tool call, or that reference missing/already-linked grade IDs, are
    reported in the response and skipped. Other valid decisions in the same
    batch are still persisted.

    Slack alerts for flagged tool calls fire from here (not from grading): only
    once the decision is uploaded are the coding agent (from the session) and the
    Analyzer deep link available. Alerts fire once per decision — only for
    decisions newly inserted by this call, so re-pushes (e.g. pending ->
    resolved) do not re-notify.

    Args:
        body (ToolCallDecisionBatchRequest): Batch upload tool-call decisions after transcript
            ingest.

            Every decision should refer to a tool-use block already present in the
            session's messages. Valid decisions are persisted even when other items in
            the same batch cannot be resolved.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | ToolCallDecisionBatchResponse
    """

    return sync_detailed(
        client=client,
        body=body,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient | Client,
    body: ToolCallDecisionBatchRequest,
) -> Response[HTTPValidationError | ToolCallDecisionBatchResponse]:
    """Upload Tool Call Decisions Batch

     Persist decisions for already-ingested tool calls, alerting on newly flagged ones.

    This endpoint is intentionally batch-oriented and post-ingest-only. The
    transcript must already exist in Watcher so each decision can be resolved to
    a canonical session message. Decisions that cannot be resolved to an
    ingested tool call, or that reference missing/already-linked grade IDs, are
    reported in the response and skipped. Other valid decisions in the same
    batch are still persisted.

    Slack alerts for flagged tool calls fire from here (not from grading): only
    once the decision is uploaded are the coding agent (from the session) and the
    Analyzer deep link available. Alerts fire once per decision — only for
    decisions newly inserted by this call, so re-pushes (e.g. pending ->
    resolved) do not re-notify.

    Args:
        body (ToolCallDecisionBatchRequest): Batch upload tool-call decisions after transcript
            ingest.

            Every decision should refer to a tool-use block already present in the
            session's messages. Valid decisions are persisted even when other items in
            the same batch cannot be resolved.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | ToolCallDecisionBatchResponse]
    """

    kwargs = _get_kwargs(
        body=body,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient | Client,
    body: ToolCallDecisionBatchRequest,
) -> HTTPValidationError | ToolCallDecisionBatchResponse | None:
    """Upload Tool Call Decisions Batch

     Persist decisions for already-ingested tool calls, alerting on newly flagged ones.

    This endpoint is intentionally batch-oriented and post-ingest-only. The
    transcript must already exist in Watcher so each decision can be resolved to
    a canonical session message. Decisions that cannot be resolved to an
    ingested tool call, or that reference missing/already-linked grade IDs, are
    reported in the response and skipped. Other valid decisions in the same
    batch are still persisted.

    Slack alerts for flagged tool calls fire from here (not from grading): only
    once the decision is uploaded are the coding agent (from the session) and the
    Analyzer deep link available. Alerts fire once per decision — only for
    decisions newly inserted by this call, so re-pushes (e.g. pending ->
    resolved) do not re-notify.

    Args:
        body (ToolCallDecisionBatchRequest): Batch upload tool-call decisions after transcript
            ingest.

            Every decision should refer to a tool-use block already present in the
            session's messages. Valid decisions are persisted even when other items in
            the same batch cannot be resolved.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | ToolCallDecisionBatchResponse
    """

    return (
        await asyncio_detailed(
            client=client,
            body=body,
        )
    ).parsed
