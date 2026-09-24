from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.session_list_response import SessionListResponse
from ...models.session_search_params import SessionSearchParams
from ...types import Response


def _get_kwargs(
    *,
    body: SessionSearchParams,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/v1/sessions/search",
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
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
    body: SessionSearchParams,
) -> Response[HTTPValidationError | SessionListResponse]:
    """Search Sessions Endpoint

     Search sessions with filtering, pagination, and sort. Same read-scope rules as GET /sessions.

    Sessions with no recorded messages never match, whatever the filters.

    Args:
        body (SessionSearchParams): Request body for POST /sessions/search.

            Supports all filtering, pagination, and sort options.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | SessionListResponse]
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
    body: SessionSearchParams,
) -> HTTPValidationError | SessionListResponse | None:
    """Search Sessions Endpoint

     Search sessions with filtering, pagination, and sort. Same read-scope rules as GET /sessions.

    Sessions with no recorded messages never match, whatever the filters.

    Args:
        body (SessionSearchParams): Request body for POST /sessions/search.

            Supports all filtering, pagination, and sort options.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | SessionListResponse
    """

    return sync_detailed(
        client=client,
        body=body,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient | Client,
    body: SessionSearchParams,
) -> Response[HTTPValidationError | SessionListResponse]:
    """Search Sessions Endpoint

     Search sessions with filtering, pagination, and sort. Same read-scope rules as GET /sessions.

    Sessions with no recorded messages never match, whatever the filters.

    Args:
        body (SessionSearchParams): Request body for POST /sessions/search.

            Supports all filtering, pagination, and sort options.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | SessionListResponse]
    """

    kwargs = _get_kwargs(
        body=body,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient | Client,
    body: SessionSearchParams,
) -> HTTPValidationError | SessionListResponse | None:
    """Search Sessions Endpoint

     Search sessions with filtering, pagination, and sort. Same read-scope rules as GET /sessions.

    Sessions with no recorded messages never match, whatever the filters.

    Args:
        body (SessionSearchParams): Request body for POST /sessions/search.

            Supports all filtering, pagination, and sort options.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | SessionListResponse
    """

    return (
        await asyncio_detailed(
            client=client,
            body=body,
        )
    ).parsed
