from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.device_authorization_response import DeviceAuthorizationResponse
from ...types import Response


def _get_kwargs() -> dict[str, Any]:

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/v1/auth/device/authorize",
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> DeviceAuthorizationResponse | None:
    if response.status_code == 200:
        response_200 = DeviceAuthorizationResponse.from_dict(response.json())

        return response_200

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Response[DeviceAuthorizationResponse]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient | Client,
) -> Response[DeviceAuthorizationResponse]:
    """Auth Device Authorize

     Start a device-authorization sign-in (RFC 8628) for a headless client.

    Unauthenticated by design — it produces credentials. Proxies WorkOS's
    device-authorization endpoint so clients need nothing but this server's
    URL; the WorkOS client id stays server-side configuration.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[DeviceAuthorizationResponse]
    """

    kwargs = _get_kwargs()

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient | Client,
) -> DeviceAuthorizationResponse | None:
    """Auth Device Authorize

     Start a device-authorization sign-in (RFC 8628) for a headless client.

    Unauthenticated by design — it produces credentials. Proxies WorkOS's
    device-authorization endpoint so clients need nothing but this server's
    URL; the WorkOS client id stays server-side configuration.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        DeviceAuthorizationResponse
    """

    return sync_detailed(
        client=client,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient | Client,
) -> Response[DeviceAuthorizationResponse]:
    """Auth Device Authorize

     Start a device-authorization sign-in (RFC 8628) for a headless client.

    Unauthenticated by design — it produces credentials. Proxies WorkOS's
    device-authorization endpoint so clients need nothing but this server's
    URL; the WorkOS client id stays server-side configuration.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[DeviceAuthorizationResponse]
    """

    kwargs = _get_kwargs()

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient | Client,
) -> DeviceAuthorizationResponse | None:
    """Auth Device Authorize

     Start a device-authorization sign-in (RFC 8628) for a headless client.

    Unauthenticated by design — it produces credentials. Proxies WorkOS's
    device-authorization endpoint so clients need nothing but this server's
    URL; the WorkOS client id stays server-side configuration.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        DeviceAuthorizationResponse
    """

    return (
        await asyncio_detailed(
            client=client,
        )
    ).parsed
