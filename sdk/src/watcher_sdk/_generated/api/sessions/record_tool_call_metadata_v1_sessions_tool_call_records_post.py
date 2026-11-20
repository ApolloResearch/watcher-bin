from http import HTTPStatus
from typing import Any, cast

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.tool_call_records_request import ToolCallRecordsRequest
from ...models.tool_call_records_response import ToolCallRecordsResponse
from ...types import Response


def _get_kwargs(
    *,
    body: ToolCallRecordsRequest,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/v1/sessions/tool-call-records",
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Any | HTTPValidationError | ToolCallRecordsResponse | None:
    if response.status_code == 200:
        response_200 = ToolCallRecordsResponse.from_dict(response.json())

        return response_200

    if response.status_code == 400:
        response_400 = cast(Any, None)
        return response_400

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
) -> Response[Any | HTTPValidationError | ToolCallRecordsResponse]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient | Client,
    body: ToolCallRecordsRequest,
) -> Response[Any | HTTPValidationError | ToolCallRecordsResponse]:
    """Record Tool Call Metadata

     Record tool calls Watcher observed but did not grade, without their content.

    Each record holds only the call's ID, tool name, observation time and the
    reason Watcher did not grade it (``watcher_ignore`` for a call in a
    session a ``.watcher-ignore`` marker covered). Requests with any other
    field are rejected with 422, so no tool input, output, working directory
    or message text can be sent.

    The session is found or created from ``agent_session_id`` as
    ``POST /v1/ingest`` finds it, matching only sessions within the caller's
    write scope and never changing an owner. A session created here has no
    messages and stays out of session lists until its transcript arrives. A
    temporary recording conflict returns 503 with ``Retry-After``; retry the
    request with bounded backoff.

    A recorded call becomes an ordinary tool call, linked to its message, as
    soon as Watcher holds that message, whichever arrives first. Records are
    idempotent per call; a record never downgrades a call Watcher already
    evaluated, and a record for a call whose verdict was kept when retention
    removed the session's content is acknowledged without being stored. Each result
    says what the record did and what Watcher now holds for the call.

    Args:
        body (ToolCallRecordsRequest): Records of one agent session's ungraded tool calls.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError | ToolCallRecordsResponse]
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
    body: ToolCallRecordsRequest,
) -> Any | HTTPValidationError | ToolCallRecordsResponse | None:
    """Record Tool Call Metadata

     Record tool calls Watcher observed but did not grade, without their content.

    Each record holds only the call's ID, tool name, observation time and the
    reason Watcher did not grade it (``watcher_ignore`` for a call in a
    session a ``.watcher-ignore`` marker covered). Requests with any other
    field are rejected with 422, so no tool input, output, working directory
    or message text can be sent.

    The session is found or created from ``agent_session_id`` as
    ``POST /v1/ingest`` finds it, matching only sessions within the caller's
    write scope and never changing an owner. A session created here has no
    messages and stays out of session lists until its transcript arrives. A
    temporary recording conflict returns 503 with ``Retry-After``; retry the
    request with bounded backoff.

    A recorded call becomes an ordinary tool call, linked to its message, as
    soon as Watcher holds that message, whichever arrives first. Records are
    idempotent per call; a record never downgrades a call Watcher already
    evaluated, and a record for a call whose verdict was kept when retention
    removed the session's content is acknowledged without being stored. Each result
    says what the record did and what Watcher now holds for the call.

    Args:
        body (ToolCallRecordsRequest): Records of one agent session's ungraded tool calls.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError | ToolCallRecordsResponse
    """

    return sync_detailed(
        client=client,
        body=body,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient | Client,
    body: ToolCallRecordsRequest,
) -> Response[Any | HTTPValidationError | ToolCallRecordsResponse]:
    """Record Tool Call Metadata

     Record tool calls Watcher observed but did not grade, without their content.

    Each record holds only the call's ID, tool name, observation time and the
    reason Watcher did not grade it (``watcher_ignore`` for a call in a
    session a ``.watcher-ignore`` marker covered). Requests with any other
    field are rejected with 422, so no tool input, output, working directory
    or message text can be sent.

    The session is found or created from ``agent_session_id`` as
    ``POST /v1/ingest`` finds it, matching only sessions within the caller's
    write scope and never changing an owner. A session created here has no
    messages and stays out of session lists until its transcript arrives. A
    temporary recording conflict returns 503 with ``Retry-After``; retry the
    request with bounded backoff.

    A recorded call becomes an ordinary tool call, linked to its message, as
    soon as Watcher holds that message, whichever arrives first. Records are
    idempotent per call; a record never downgrades a call Watcher already
    evaluated, and a record for a call whose verdict was kept when retention
    removed the session's content is acknowledged without being stored. Each result
    says what the record did and what Watcher now holds for the call.

    Args:
        body (ToolCallRecordsRequest): Records of one agent session's ungraded tool calls.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError | ToolCallRecordsResponse]
    """

    kwargs = _get_kwargs(
        body=body,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient | Client,
    body: ToolCallRecordsRequest,
) -> Any | HTTPValidationError | ToolCallRecordsResponse | None:
    """Record Tool Call Metadata

     Record tool calls Watcher observed but did not grade, without their content.

    Each record holds only the call's ID, tool name, observation time and the
    reason Watcher did not grade it (``watcher_ignore`` for a call in a
    session a ``.watcher-ignore`` marker covered). Requests with any other
    field are rejected with 422, so no tool input, output, working directory
    or message text can be sent.

    The session is found or created from ``agent_session_id`` as
    ``POST /v1/ingest`` finds it, matching only sessions within the caller's
    write scope and never changing an owner. A session created here has no
    messages and stays out of session lists until its transcript arrives. A
    temporary recording conflict returns 503 with ``Retry-After``; retry the
    request with bounded backoff.

    A recorded call becomes an ordinary tool call, linked to its message, as
    soon as Watcher holds that message, whichever arrives first. Records are
    idempotent per call; a record never downgrades a call Watcher already
    evaluated, and a record for a call whose verdict was kept when retention
    removed the session's content is acknowledged without being stored. Each result
    says what the record did and what Watcher now holds for the call.

    Args:
        body (ToolCallRecordsRequest): Records of one agent session's ungraded tool calls.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError | ToolCallRecordsResponse
    """

    return (
        await asyncio_detailed(
            client=client,
            body=body,
        )
    ).parsed
