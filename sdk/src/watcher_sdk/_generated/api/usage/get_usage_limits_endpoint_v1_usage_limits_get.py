from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.usage_limits_response import UsageLimitsResponse
from ...types import Response


def _get_kwargs() -> dict[str, Any]:

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/v1/usage/limits",
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> UsageLimitsResponse | None:
    if response.status_code == 200:
        response_200 = UsageLimitsResponse.from_dict(response.json())

        return response_200

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Response[UsageLimitsResponse]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient | Client,
) -> Response[UsageLimitsResponse]:
    """Get Usage Limits Endpoint

     Return whether grading is currently capped for the caller's org, and the call figures behind it.

    Readable by any org member — no permission gate — since it backs the
    grading-paused alert on member-visible pages and carries nothing sensitive.

    Runs the same check the grade routes run, so the readout cannot drift from
    what blocks — including its 500 when the counter cannot be read, rather than
    reporting a cap status we could not verify.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[UsageLimitsResponse]
    """

    kwargs = _get_kwargs()

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient | Client,
) -> UsageLimitsResponse | None:
    """Get Usage Limits Endpoint

     Return whether grading is currently capped for the caller's org, and the call figures behind it.

    Readable by any org member — no permission gate — since it backs the
    grading-paused alert on member-visible pages and carries nothing sensitive.

    Runs the same check the grade routes run, so the readout cannot drift from
    what blocks — including its 500 when the counter cannot be read, rather than
    reporting a cap status we could not verify.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        UsageLimitsResponse
    """

    return sync_detailed(
        client=client,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient | Client,
) -> Response[UsageLimitsResponse]:
    """Get Usage Limits Endpoint

     Return whether grading is currently capped for the caller's org, and the call figures behind it.

    Readable by any org member — no permission gate — since it backs the
    grading-paused alert on member-visible pages and carries nothing sensitive.

    Runs the same check the grade routes run, so the readout cannot drift from
    what blocks — including its 500 when the counter cannot be read, rather than
    reporting a cap status we could not verify.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[UsageLimitsResponse]
    """

    kwargs = _get_kwargs()

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient | Client,
) -> UsageLimitsResponse | None:
    """Get Usage Limits Endpoint

     Return whether grading is currently capped for the caller's org, and the call figures behind it.

    Readable by any org member — no permission gate — since it backs the
    grading-paused alert on member-visible pages and carries nothing sensitive.

    Runs the same check the grade routes run, so the readout cannot drift from
    what blocks — including its 500 when the counter cannot be read, rather than
    reporting a cap status we could not verify.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        UsageLimitsResponse
    """

    return (
        await asyncio_detailed(
            client=client,
        )
    ).parsed
