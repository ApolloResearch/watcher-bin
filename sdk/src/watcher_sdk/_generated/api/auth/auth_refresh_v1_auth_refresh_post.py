from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.refresh_request import RefreshRequest
from ...models.token_response import TokenResponse
from ...types import Response


def _get_kwargs(
    *,
    body: RefreshRequest,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/v1/auth/refresh",
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> HTTPValidationError | TokenResponse | None:
    if response.status_code == 200:
        response_200 = TokenResponse.from_dict(response.json())

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
) -> Response[HTTPValidationError | TokenResponse]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient | Client,
    body: RefreshRequest,
) -> Response[HTTPValidationError | TokenResponse]:
    """Auth Refresh

     Refresh an expired access token.

    The refresh token is read from the httpOnly cookie (set by /callback) or from
    the request body for server-side callers that store it and send it explicitly
    (e.g. Watcher proxy, scripts).

    Args:
        body (RefreshRequest): Request body for POST /v1/auth/refresh.

            The refresh_token is optional — the backend also reads it from an
            httpOnly cookie set during the callback flow.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | TokenResponse]
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
    body: RefreshRequest,
) -> HTTPValidationError | TokenResponse | None:
    """Auth Refresh

     Refresh an expired access token.

    The refresh token is read from the httpOnly cookie (set by /callback) or from
    the request body for server-side callers that store it and send it explicitly
    (e.g. Watcher proxy, scripts).

    Args:
        body (RefreshRequest): Request body for POST /v1/auth/refresh.

            The refresh_token is optional — the backend also reads it from an
            httpOnly cookie set during the callback flow.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | TokenResponse
    """

    return sync_detailed(
        client=client,
        body=body,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient | Client,
    body: RefreshRequest,
) -> Response[HTTPValidationError | TokenResponse]:
    """Auth Refresh

     Refresh an expired access token.

    The refresh token is read from the httpOnly cookie (set by /callback) or from
    the request body for server-side callers that store it and send it explicitly
    (e.g. Watcher proxy, scripts).

    Args:
        body (RefreshRequest): Request body for POST /v1/auth/refresh.

            The refresh_token is optional — the backend also reads it from an
            httpOnly cookie set during the callback flow.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | TokenResponse]
    """

    kwargs = _get_kwargs(
        body=body,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient | Client,
    body: RefreshRequest,
) -> HTTPValidationError | TokenResponse | None:
    """Auth Refresh

     Refresh an expired access token.

    The refresh token is read from the httpOnly cookie (set by /callback) or from
    the request body for server-side callers that store it and send it explicitly
    (e.g. Watcher proxy, scripts).

    Args:
        body (RefreshRequest): Request body for POST /v1/auth/refresh.

            The refresh_token is optional — the backend also reads it from an
            httpOnly cookie set during the callback flow.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | TokenResponse
    """

    return (
        await asyncio_detailed(
            client=client,
            body=body,
        )
    ).parsed
