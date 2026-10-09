from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.tool_call_list_response import ToolCallListResponse
from ...models.tool_call_search_params import ToolCallSearchParams
from ...types import Response


def _get_kwargs(
    *,
    body: ToolCallSearchParams,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/v1/tool-calls/search",
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> HTTPValidationError | ToolCallListResponse | None:
    if response.status_code == 200:
        response_200 = ToolCallListResponse.from_dict(response.json())

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
) -> Response[HTTPValidationError | ToolCallListResponse]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient | Client,
    body: ToolCallSearchParams,
) -> Response[HTTPValidationError | ToolCallListResponse]:
    """Search Tool Calls Endpoint

     Search tool calls with filtering, pagination, and sort.

    Read scope matches the sessions list exactly: a caller holding
    ``sessions:findings:read:any`` sees the whole organization and may filter by any owner,
    while everyone else is confined to their own calls and naming somebody else is
    refused rather than silently answered about themselves.

    Only calls Watcher recorded a decision about are listed, which is the same
    population the dashboard's tool-call counts are computed over.

    Args:
        body (ToolCallSearchParams): Request body for POST /tool-calls/search.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | ToolCallListResponse]
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
    body: ToolCallSearchParams,
) -> HTTPValidationError | ToolCallListResponse | None:
    """Search Tool Calls Endpoint

     Search tool calls with filtering, pagination, and sort.

    Read scope matches the sessions list exactly: a caller holding
    ``sessions:findings:read:any`` sees the whole organization and may filter by any owner,
    while everyone else is confined to their own calls and naming somebody else is
    refused rather than silently answered about themselves.

    Only calls Watcher recorded a decision about are listed, which is the same
    population the dashboard's tool-call counts are computed over.

    Args:
        body (ToolCallSearchParams): Request body for POST /tool-calls/search.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | ToolCallListResponse
    """

    return sync_detailed(
        client=client,
        body=body,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient | Client,
    body: ToolCallSearchParams,
) -> Response[HTTPValidationError | ToolCallListResponse]:
    """Search Tool Calls Endpoint

     Search tool calls with filtering, pagination, and sort.

    Read scope matches the sessions list exactly: a caller holding
    ``sessions:findings:read:any`` sees the whole organization and may filter by any owner,
    while everyone else is confined to their own calls and naming somebody else is
    refused rather than silently answered about themselves.

    Only calls Watcher recorded a decision about are listed, which is the same
    population the dashboard's tool-call counts are computed over.

    Args:
        body (ToolCallSearchParams): Request body for POST /tool-calls/search.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | ToolCallListResponse]
    """

    kwargs = _get_kwargs(
        body=body,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient | Client,
    body: ToolCallSearchParams,
) -> HTTPValidationError | ToolCallListResponse | None:
    """Search Tool Calls Endpoint

     Search tool calls with filtering, pagination, and sort.

    Read scope matches the sessions list exactly: a caller holding
    ``sessions:findings:read:any`` sees the whole organization and may filter by any owner,
    while everyone else is confined to their own calls and naming somebody else is
    refused rather than silently answered about themselves.

    Only calls Watcher recorded a decision about are listed, which is the same
    population the dashboard's tool-call counts are computed over.

    Args:
        body (ToolCallSearchParams): Request body for POST /tool-calls/search.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | ToolCallListResponse
    """

    return (
        await asyncio_detailed(
            client=client,
            body=body,
        )
    ).parsed
