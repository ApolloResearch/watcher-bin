from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.create_grader_request import CreateGraderRequest
from ...models.grader_detail import GraderDetail
from ...models.http_validation_error import HTTPValidationError
from ...types import Response


def _get_kwargs(
    *,
    body: CreateGraderRequest,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/v1/graders",
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> GraderDetail | HTTPValidationError | None:
    if response.status_code == 201:
        response_201 = GraderDetail.from_dict(response.json())

        return response_201

    if response.status_code == 422:
        response_422 = HTTPValidationError.from_dict(response.json())

        return response_422

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Response[GraderDetail | HTTPValidationError]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient | Client,
    body: CreateGraderRequest,
) -> Response[GraderDetail | HTTPValidationError]:
    """Create Grader Endpoint

     Create version 0 of a grader in your organization.

    Requires an authenticated user, who becomes the grader's owner. API keys
    cannot create graders (403).

    Args:
        body (CreateGraderRequest): Request body for POST /v1/graders.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[GraderDetail | HTTPValidationError]
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
    body: CreateGraderRequest,
) -> GraderDetail | HTTPValidationError | None:
    """Create Grader Endpoint

     Create version 0 of a grader in your organization.

    Requires an authenticated user, who becomes the grader's owner. API keys
    cannot create graders (403).

    Args:
        body (CreateGraderRequest): Request body for POST /v1/graders.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        GraderDetail | HTTPValidationError
    """

    return sync_detailed(
        client=client,
        body=body,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient | Client,
    body: CreateGraderRequest,
) -> Response[GraderDetail | HTTPValidationError]:
    """Create Grader Endpoint

     Create version 0 of a grader in your organization.

    Requires an authenticated user, who becomes the grader's owner. API keys
    cannot create graders (403).

    Args:
        body (CreateGraderRequest): Request body for POST /v1/graders.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[GraderDetail | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        body=body,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient | Client,
    body: CreateGraderRequest,
) -> GraderDetail | HTTPValidationError | None:
    """Create Grader Endpoint

     Create version 0 of a grader in your organization.

    Requires an authenticated user, who becomes the grader's owner. API keys
    cannot create graders (403).

    Args:
        body (CreateGraderRequest): Request body for POST /v1/graders.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        GraderDetail | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            client=client,
            body=body,
        )
    ).parsed
