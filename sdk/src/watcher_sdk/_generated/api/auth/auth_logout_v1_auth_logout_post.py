from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.auth_logout_v1_auth_logout_post_response_auth_logout_v1_auth_logout_post import (
    AuthLogoutV1AuthLogoutPostResponseAuthLogoutV1AuthLogoutPost,
)
from ...types import Response


def _get_kwargs() -> dict[str, Any]:

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/v1/auth/logout",
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> AuthLogoutV1AuthLogoutPostResponseAuthLogoutV1AuthLogoutPost | None:
    if response.status_code == 200:
        response_200 = (
            AuthLogoutV1AuthLogoutPostResponseAuthLogoutV1AuthLogoutPost.from_dict(
                response.json()
            )
        )

        return response_200

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Response[AuthLogoutV1AuthLogoutPostResponseAuthLogoutV1AuthLogoutPost]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient | Client,
) -> Response[AuthLogoutV1AuthLogoutPostResponseAuthLogoutV1AuthLogoutPost]:
    """Auth Logout

     Log out the user — revokes the WorkOS session and clears the refresh cookie.

    Reads the ``sid`` (session ID) from the JWT in the Authorization header
    and calls WorkOS to revoke the session server-side. This ensures the user
    must fully re-authenticate on next login (no auto-complete from a cached
    WorkOS session).

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[AuthLogoutV1AuthLogoutPostResponseAuthLogoutV1AuthLogoutPost]
    """

    kwargs = _get_kwargs()

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient | Client,
) -> AuthLogoutV1AuthLogoutPostResponseAuthLogoutV1AuthLogoutPost | None:
    """Auth Logout

     Log out the user — revokes the WorkOS session and clears the refresh cookie.

    Reads the ``sid`` (session ID) from the JWT in the Authorization header
    and calls WorkOS to revoke the session server-side. This ensures the user
    must fully re-authenticate on next login (no auto-complete from a cached
    WorkOS session).

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        AuthLogoutV1AuthLogoutPostResponseAuthLogoutV1AuthLogoutPost
    """

    return sync_detailed(
        client=client,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient | Client,
) -> Response[AuthLogoutV1AuthLogoutPostResponseAuthLogoutV1AuthLogoutPost]:
    """Auth Logout

     Log out the user — revokes the WorkOS session and clears the refresh cookie.

    Reads the ``sid`` (session ID) from the JWT in the Authorization header
    and calls WorkOS to revoke the session server-side. This ensures the user
    must fully re-authenticate on next login (no auto-complete from a cached
    WorkOS session).

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[AuthLogoutV1AuthLogoutPostResponseAuthLogoutV1AuthLogoutPost]
    """

    kwargs = _get_kwargs()

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient | Client,
) -> AuthLogoutV1AuthLogoutPostResponseAuthLogoutV1AuthLogoutPost | None:
    """Auth Logout

     Log out the user — revokes the WorkOS session and clears the refresh cookie.

    Reads the ``sid`` (session ID) from the JWT in the Authorization header
    and calls WorkOS to revoke the session server-side. This ensures the user
    must fully re-authenticate on next login (no auto-complete from a cached
    WorkOS session).

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        AuthLogoutV1AuthLogoutPostResponseAuthLogoutV1AuthLogoutPost
    """

    return (
        await asyncio_detailed(
            client=client,
        )
    ).parsed
