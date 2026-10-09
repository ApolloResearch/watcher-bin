from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.auth_client_config import AuthClientConfig
from ...types import Response


def _get_kwargs() -> dict[str, Any]:

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/v1/auth/client-config",
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> AuthClientConfig | None:
    if response.status_code == 200:
        response_200 = AuthClientConfig.from_dict(response.json())

        return response_200

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Response[AuthClientConfig]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient | Client,
) -> Response[AuthClientConfig]:
    """Auth Client Config

     Return the deployment's public auth configuration.

    Unauthenticated by design: clients (analyzer SPA, watcher CLI/hooks)
    call this to discover the auth mode and, in WorkOS mode, the client id
    to start a sign-in with, so the value is configured once server-side
    instead of being baked into each client.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[AuthClientConfig]
    """

    kwargs = _get_kwargs()

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient | Client,
) -> AuthClientConfig | None:
    """Auth Client Config

     Return the deployment's public auth configuration.

    Unauthenticated by design: clients (analyzer SPA, watcher CLI/hooks)
    call this to discover the auth mode and, in WorkOS mode, the client id
    to start a sign-in with, so the value is configured once server-side
    instead of being baked into each client.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        AuthClientConfig
    """

    return sync_detailed(
        client=client,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient | Client,
) -> Response[AuthClientConfig]:
    """Auth Client Config

     Return the deployment's public auth configuration.

    Unauthenticated by design: clients (analyzer SPA, watcher CLI/hooks)
    call this to discover the auth mode and, in WorkOS mode, the client id
    to start a sign-in with, so the value is configured once server-side
    instead of being baked into each client.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[AuthClientConfig]
    """

    kwargs = _get_kwargs()

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient | Client,
) -> AuthClientConfig | None:
    """Auth Client Config

     Return the deployment's public auth configuration.

    Unauthenticated by design: clients (analyzer SPA, watcher CLI/hooks)
    call this to discover the auth mode and, in WorkOS mode, the client id
    to start a sign-in with, so the value is configured once server-side
    instead of being baked into each client.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        AuthClientConfig
    """

    return (
        await asyncio_detailed(
            client=client,
        )
    ).parsed
