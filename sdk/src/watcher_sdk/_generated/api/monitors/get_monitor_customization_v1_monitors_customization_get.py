from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.monitor_customization_response import MonitorCustomizationResponse
from ...types import Response


def _get_kwargs() -> dict[str, Any]:

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/v1/monitors/customization",
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> MonitorCustomizationResponse | None:
    if response.status_code == 200:
        response_200 = MonitorCustomizationResponse.from_dict(response.json())

        return response_200

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Response[MonitorCustomizationResponse]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient | Client,
) -> Response[MonitorCustomizationResponse]:
    """Get Monitor Customization

     Return the org's monitor customization (empty instructions when never set).

    This is the whole customization surface an admin sees for the monitors:
    their own text plus each monitor's description (from GET /v1/monitors).

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[MonitorCustomizationResponse]
    """

    kwargs = _get_kwargs()

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient | Client,
) -> MonitorCustomizationResponse | None:
    """Get Monitor Customization

     Return the org's monitor customization (empty instructions when never set).

    This is the whole customization surface an admin sees for the monitors:
    their own text plus each monitor's description (from GET /v1/monitors).

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        MonitorCustomizationResponse
    """

    return sync_detailed(
        client=client,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient | Client,
) -> Response[MonitorCustomizationResponse]:
    """Get Monitor Customization

     Return the org's monitor customization (empty instructions when never set).

    This is the whole customization surface an admin sees for the monitors:
    their own text plus each monitor's description (from GET /v1/monitors).

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[MonitorCustomizationResponse]
    """

    kwargs = _get_kwargs()

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient | Client,
) -> MonitorCustomizationResponse | None:
    """Get Monitor Customization

     Return the org's monitor customization (empty instructions when never set).

    This is the whole customization surface an admin sees for the monitors:
    their own text plus each monitor's description (from GET /v1/monitors).

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        MonitorCustomizationResponse
    """

    return (
        await asyncio_detailed(
            client=client,
        )
    ).parsed
