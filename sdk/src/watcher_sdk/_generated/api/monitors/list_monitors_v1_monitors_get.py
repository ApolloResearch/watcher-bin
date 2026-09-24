from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.monitors_response import MonitorsResponse
from ...types import Response


def _get_kwargs() -> dict[str, Any]:

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/v1/monitors",
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> MonitorsResponse | None:
    if response.status_code == 200:
        response_200 = MonitorsResponse.from_dict(response.json())

        return response_200

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Response[MonitorsResponse]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient | Client,
) -> Response[MonitorsResponse]:
    """List Monitors

     List the server-managed monitors, with their client-facing facts.

    Requires only authentication (any org member): the response carries no
    org data and no monitor internals — name, description, context policy, and
    token budget only, never the prompt or model.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[MonitorsResponse]
    """

    kwargs = _get_kwargs()

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient | Client,
) -> MonitorsResponse | None:
    """List Monitors

     List the server-managed monitors, with their client-facing facts.

    Requires only authentication (any org member): the response carries no
    org data and no monitor internals — name, description, context policy, and
    token budget only, never the prompt or model.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        MonitorsResponse
    """

    return sync_detailed(
        client=client,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient | Client,
) -> Response[MonitorsResponse]:
    """List Monitors

     List the server-managed monitors, with their client-facing facts.

    Requires only authentication (any org member): the response carries no
    org data and no monitor internals — name, description, context policy, and
    token budget only, never the prompt or model.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[MonitorsResponse]
    """

    kwargs = _get_kwargs()

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient | Client,
) -> MonitorsResponse | None:
    """List Monitors

     List the server-managed monitors, with their client-facing facts.

    Requires only authentication (any org member): the response carries no
    org data and no monitor internals — name, description, context policy, and
    token budget only, never the prompt or model.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        MonitorsResponse
    """

    return (
        await asyncio_detailed(
            client=client,
        )
    ).parsed
