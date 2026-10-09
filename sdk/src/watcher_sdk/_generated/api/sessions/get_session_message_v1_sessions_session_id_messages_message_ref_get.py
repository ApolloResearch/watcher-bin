from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.message_detail_response import MessageDetailResponse
from ...types import Response


def _get_kwargs(
    session_id: str,
    message_ref: str,
) -> dict[str, Any]:

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/v1/sessions/{session_id}/messages/{message_ref}".format(
            session_id=quote(str(session_id), safe=""),
            message_ref=quote(str(message_ref), safe=""),
        ),
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> HTTPValidationError | MessageDetailResponse | None:
    if response.status_code == 200:
        response_200 = MessageDetailResponse.from_dict(response.json())

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
) -> Response[HTTPValidationError | MessageDetailResponse]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    session_id: str,
    message_ref: str,
    *,
    client: AuthenticatedClient | Client,
) -> Response[HTTPValidationError | MessageDetailResponse]:
    """Get Session Message

     Get one message's full stored content by its ``message_ref``.

    Backs per-elision expansion: the truncated trajectory view marks what it
    elided and carries each message's ``message_ref``; this endpoint returns
    that single message with full content, so expanding one item never
    refetches (or renders) the whole trajectory. There is no ``view`` param —
    the truncated form is what the trajectory response already provides.
    Extended-thinking replay payloads are stripped like every other read path.

    Requires ownership, ``sessions:content:read:any``, or an active session content
    approval. Returns 404 for inaccessible or scrubbed content and for refs not in the session.

    Args:
        session_id (str):
        message_ref (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | MessageDetailResponse]
    """

    kwargs = _get_kwargs(
        session_id=session_id,
        message_ref=message_ref,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    session_id: str,
    message_ref: str,
    *,
    client: AuthenticatedClient | Client,
) -> HTTPValidationError | MessageDetailResponse | None:
    """Get Session Message

     Get one message's full stored content by its ``message_ref``.

    Backs per-elision expansion: the truncated trajectory view marks what it
    elided and carries each message's ``message_ref``; this endpoint returns
    that single message with full content, so expanding one item never
    refetches (or renders) the whole trajectory. There is no ``view`` param —
    the truncated form is what the trajectory response already provides.
    Extended-thinking replay payloads are stripped like every other read path.

    Requires ownership, ``sessions:content:read:any``, or an active session content
    approval. Returns 404 for inaccessible or scrubbed content and for refs not in the session.

    Args:
        session_id (str):
        message_ref (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | MessageDetailResponse
    """

    return sync_detailed(
        session_id=session_id,
        message_ref=message_ref,
        client=client,
    ).parsed


async def asyncio_detailed(
    session_id: str,
    message_ref: str,
    *,
    client: AuthenticatedClient | Client,
) -> Response[HTTPValidationError | MessageDetailResponse]:
    """Get Session Message

     Get one message's full stored content by its ``message_ref``.

    Backs per-elision expansion: the truncated trajectory view marks what it
    elided and carries each message's ``message_ref``; this endpoint returns
    that single message with full content, so expanding one item never
    refetches (or renders) the whole trajectory. There is no ``view`` param —
    the truncated form is what the trajectory response already provides.
    Extended-thinking replay payloads are stripped like every other read path.

    Requires ownership, ``sessions:content:read:any``, or an active session content
    approval. Returns 404 for inaccessible or scrubbed content and for refs not in the session.

    Args:
        session_id (str):
        message_ref (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | MessageDetailResponse]
    """

    kwargs = _get_kwargs(
        session_id=session_id,
        message_ref=message_ref,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    session_id: str,
    message_ref: str,
    *,
    client: AuthenticatedClient | Client,
) -> HTTPValidationError | MessageDetailResponse | None:
    """Get Session Message

     Get one message's full stored content by its ``message_ref``.

    Backs per-elision expansion: the truncated trajectory view marks what it
    elided and carries each message's ``message_ref``; this endpoint returns
    that single message with full content, so expanding one item never
    refetches (or renders) the whole trajectory. There is no ``view`` param —
    the truncated form is what the trajectory response already provides.
    Extended-thinking replay payloads are stripped like every other read path.

    Requires ownership, ``sessions:content:read:any``, or an active session content
    approval. Returns 404 for inaccessible or scrubbed content and for refs not in the session.

    Args:
        session_id (str):
        message_ref (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | MessageDetailResponse
    """

    return (
        await asyncio_detailed(
            session_id=session_id,
            message_ref=message_ref,
            client=client,
        )
    ).parsed
