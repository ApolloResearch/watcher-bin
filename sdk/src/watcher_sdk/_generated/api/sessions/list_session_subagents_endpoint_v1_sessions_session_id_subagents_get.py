from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.subagent_list_response import SubagentListResponse
from ...types import UNSET, Response, Unset


def _get_kwargs(
    session_id: str,
    *,
    limit: int | Unset = 20,
    offset: int | Unset = 0,
) -> dict[str, Any]:

    params: dict[str, Any] = {}

    params["limit"] = limit

    params["offset"] = offset

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/v1/sessions/{session_id}/subagents".format(
            session_id=quote(str(session_id), safe=""),
        ),
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> HTTPValidationError | SubagentListResponse | None:
    if response.status_code == 200:
        response_200 = SubagentListResponse.from_dict(response.json())

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
) -> Response[HTTPValidationError | SubagentListResponse]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    session_id: str,
    *,
    client: AuthenticatedClient | Client,
    limit: int | Unset = 20,
    offset: int | Unset = 0,
) -> Response[HTTPValidationError | SubagentListResponse]:
    """List Session Subagents Endpoint

     List readable immediate children oldest-first, including sessions awaiting transcripts.

    Parent and child access are checked independently through ownership, findings
    or content permissions, or an active session content approval. Titles require
    ownership or blanket content permission, not temporary approval. Review status
    and severity require child findings access.
    The total counts only readable children. Return 404 for an inaccessible parent.
    Ordering uses relationship creation time, then child session ID to break ties.

    Args:
        session_id (str):
        limit (int | Unset):  Default: 20.
        offset (int | Unset):  Default: 0.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | SubagentListResponse]
    """

    kwargs = _get_kwargs(
        session_id=session_id,
        limit=limit,
        offset=offset,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    session_id: str,
    *,
    client: AuthenticatedClient | Client,
    limit: int | Unset = 20,
    offset: int | Unset = 0,
) -> HTTPValidationError | SubagentListResponse | None:
    """List Session Subagents Endpoint

     List readable immediate children oldest-first, including sessions awaiting transcripts.

    Parent and child access are checked independently through ownership, findings
    or content permissions, or an active session content approval. Titles require
    ownership or blanket content permission, not temporary approval. Review status
    and severity require child findings access.
    The total counts only readable children. Return 404 for an inaccessible parent.
    Ordering uses relationship creation time, then child session ID to break ties.

    Args:
        session_id (str):
        limit (int | Unset):  Default: 20.
        offset (int | Unset):  Default: 0.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | SubagentListResponse
    """

    return sync_detailed(
        session_id=session_id,
        client=client,
        limit=limit,
        offset=offset,
    ).parsed


async def asyncio_detailed(
    session_id: str,
    *,
    client: AuthenticatedClient | Client,
    limit: int | Unset = 20,
    offset: int | Unset = 0,
) -> Response[HTTPValidationError | SubagentListResponse]:
    """List Session Subagents Endpoint

     List readable immediate children oldest-first, including sessions awaiting transcripts.

    Parent and child access are checked independently through ownership, findings
    or content permissions, or an active session content approval. Titles require
    ownership or blanket content permission, not temporary approval. Review status
    and severity require child findings access.
    The total counts only readable children. Return 404 for an inaccessible parent.
    Ordering uses relationship creation time, then child session ID to break ties.

    Args:
        session_id (str):
        limit (int | Unset):  Default: 20.
        offset (int | Unset):  Default: 0.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | SubagentListResponse]
    """

    kwargs = _get_kwargs(
        session_id=session_id,
        limit=limit,
        offset=offset,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    session_id: str,
    *,
    client: AuthenticatedClient | Client,
    limit: int | Unset = 20,
    offset: int | Unset = 0,
) -> HTTPValidationError | SubagentListResponse | None:
    """List Session Subagents Endpoint

     List readable immediate children oldest-first, including sessions awaiting transcripts.

    Parent and child access are checked independently through ownership, findings
    or content permissions, or an active session content approval. Titles require
    ownership or blanket content permission, not temporary approval. Review status
    and severity require child findings access.
    The total counts only readable children. Return 404 for an inaccessible parent.
    Ordering uses relationship creation time, then child session ID to break ties.

    Args:
        session_id (str):
        limit (int | Unset):  Default: 20.
        offset (int | Unset):  Default: 0.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | SubagentListResponse
    """

    return (
        await asyncio_detailed(
            session_id=session_id,
            client=client,
            limit=limit,
            offset=offset,
        )
    ).parsed
