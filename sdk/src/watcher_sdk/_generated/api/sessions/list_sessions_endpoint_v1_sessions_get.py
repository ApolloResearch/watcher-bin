from http import HTTPStatus
from typing import Any
from uuid import UUID

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.session_list_response import SessionListResponse
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    limit: int | Unset = 100,
    offset: int | Unset = 0,
    sort_by: str | Unset = "ended_at",
    sort_order: str | Unset = "desc",
    user_id: None | Unset | UUID = UNSET,
) -> dict[str, Any]:

    params: dict[str, Any] = {}

    params["limit"] = limit

    params["offset"] = offset

    params["sort_by"] = sort_by

    params["sort_order"] = sort_order

    json_user_id: None | str | Unset
    if isinstance(user_id, Unset):
        json_user_id = UNSET
    elif isinstance(user_id, UUID):
        json_user_id = str(user_id)
    else:
        json_user_id = user_id
    params["user_id"] = json_user_id

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/v1/sessions",
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> HTTPValidationError | SessionListResponse | None:
    if response.status_code == 200:
        response_200 = SessionListResponse.from_dict(response.json())

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
) -> Response[HTTPValidationError | SessionListResponse]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient | Client,
    limit: int | Unset = 100,
    offset: int | Unset = 0,
    sort_by: str | Unset = "ended_at",
    sort_order: str | Unset = "desc",
    user_id: None | Unset | UUID = UNSET,
) -> Response[HTTPValidationError | SessionListResponse]:
    """List Sessions Endpoint

     List all sessions with pagination and sort. For filtered queries use POST /sessions/search.

    Callers without ``sessions:findings:read:any`` see only their own sessions
    (naming another user in ``user_id`` returns 403).

    Args:
        limit (int | Unset):  Default: 100.
        offset (int | Unset):  Default: 0.
        sort_by (str | Unset):  Default: 'ended_at'.
        sort_order (str | Unset):  Default: 'desc'.
        user_id (None | Unset | UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | SessionListResponse]
    """

    kwargs = _get_kwargs(
        limit=limit,
        offset=offset,
        sort_by=sort_by,
        sort_order=sort_order,
        user_id=user_id,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient | Client,
    limit: int | Unset = 100,
    offset: int | Unset = 0,
    sort_by: str | Unset = "ended_at",
    sort_order: str | Unset = "desc",
    user_id: None | Unset | UUID = UNSET,
) -> HTTPValidationError | SessionListResponse | None:
    """List Sessions Endpoint

     List all sessions with pagination and sort. For filtered queries use POST /sessions/search.

    Callers without ``sessions:findings:read:any`` see only their own sessions
    (naming another user in ``user_id`` returns 403).

    Args:
        limit (int | Unset):  Default: 100.
        offset (int | Unset):  Default: 0.
        sort_by (str | Unset):  Default: 'ended_at'.
        sort_order (str | Unset):  Default: 'desc'.
        user_id (None | Unset | UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | SessionListResponse
    """

    return sync_detailed(
        client=client,
        limit=limit,
        offset=offset,
        sort_by=sort_by,
        sort_order=sort_order,
        user_id=user_id,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient | Client,
    limit: int | Unset = 100,
    offset: int | Unset = 0,
    sort_by: str | Unset = "ended_at",
    sort_order: str | Unset = "desc",
    user_id: None | Unset | UUID = UNSET,
) -> Response[HTTPValidationError | SessionListResponse]:
    """List Sessions Endpoint

     List all sessions with pagination and sort. For filtered queries use POST /sessions/search.

    Callers without ``sessions:findings:read:any`` see only their own sessions
    (naming another user in ``user_id`` returns 403).

    Args:
        limit (int | Unset):  Default: 100.
        offset (int | Unset):  Default: 0.
        sort_by (str | Unset):  Default: 'ended_at'.
        sort_order (str | Unset):  Default: 'desc'.
        user_id (None | Unset | UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | SessionListResponse]
    """

    kwargs = _get_kwargs(
        limit=limit,
        offset=offset,
        sort_by=sort_by,
        sort_order=sort_order,
        user_id=user_id,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient | Client,
    limit: int | Unset = 100,
    offset: int | Unset = 0,
    sort_by: str | Unset = "ended_at",
    sort_order: str | Unset = "desc",
    user_id: None | Unset | UUID = UNSET,
) -> HTTPValidationError | SessionListResponse | None:
    """List Sessions Endpoint

     List all sessions with pagination and sort. For filtered queries use POST /sessions/search.

    Callers without ``sessions:findings:read:any`` see only their own sessions
    (naming another user in ``user_id`` returns 403).

    Args:
        limit (int | Unset):  Default: 100.
        offset (int | Unset):  Default: 0.
        sort_by (str | Unset):  Default: 'ended_at'.
        sort_order (str | Unset):  Default: 'desc'.
        user_id (None | Unset | UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | SessionListResponse
    """

    return (
        await asyncio_detailed(
            client=client,
            limit=limit,
            offset=offset,
            sort_by=sort_by,
            sort_order=sort_order,
            user_id=user_id,
        )
    ).parsed
