from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.grader_search_request import GraderSearchRequest
from ...models.grader_search_response import GraderSearchResponse
from ...models.http_validation_error import HTTPValidationError
from ...types import Response


def _get_kwargs(
    *,
    body: GraderSearchRequest,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/v1/graders/search",
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> GraderSearchResponse | HTTPValidationError | None:
    if response.status_code == 200:
        response_200 = GraderSearchResponse.from_dict(response.json())

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
) -> Response[GraderSearchResponse | HTTPValidationError]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient | Client,
    body: GraderSearchRequest,
) -> Response[GraderSearchResponse | HTTPValidationError]:
    """Search Graders Endpoint

     Search organization and built-in graders by name and header/footer content.

    Searches the latest non-archived version of each grader. Private graders
    are included only for their creator.

    Args:
        body (GraderSearchRequest): Request body for POST /v1/graders/search.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[GraderSearchResponse | HTTPValidationError]
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
    body: GraderSearchRequest,
) -> GraderSearchResponse | HTTPValidationError | None:
    """Search Graders Endpoint

     Search organization and built-in graders by name and header/footer content.

    Searches the latest non-archived version of each grader. Private graders
    are included only for their creator.

    Args:
        body (GraderSearchRequest): Request body for POST /v1/graders/search.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        GraderSearchResponse | HTTPValidationError
    """

    return sync_detailed(
        client=client,
        body=body,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient | Client,
    body: GraderSearchRequest,
) -> Response[GraderSearchResponse | HTTPValidationError]:
    """Search Graders Endpoint

     Search organization and built-in graders by name and header/footer content.

    Searches the latest non-archived version of each grader. Private graders
    are included only for their creator.

    Args:
        body (GraderSearchRequest): Request body for POST /v1/graders/search.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[GraderSearchResponse | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        body=body,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient | Client,
    body: GraderSearchRequest,
) -> GraderSearchResponse | HTTPValidationError | None:
    """Search Graders Endpoint

     Search organization and built-in graders by name and header/footer content.

    Searches the latest non-archived version of each grader. Private graders
    are included only for their creator.

    Args:
        body (GraderSearchRequest): Request body for POST /v1/graders/search.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        GraderSearchResponse | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            client=client,
            body=body,
        )
    ).parsed
