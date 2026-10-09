from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.create_session_content_access_request import (
    CreateSessionContentAccessRequest,
)
from ...models.http_validation_error import HTTPValidationError
from ...models.session_content_access_request_summary import (
    SessionContentAccessRequestSummary,
)
from ...types import Response


def _get_kwargs(
    *,
    body: CreateSessionContentAccessRequest,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/v1/users/me/session-content-access-requests",
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> HTTPValidationError | SessionContentAccessRequestSummary | None:
    if response.status_code == 200:
        response_200 = SessionContentAccessRequestSummary.from_dict(response.json())

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
) -> Response[HTTPValidationError | SessionContentAccessRequestSummary]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient | Client,
    body: CreateSessionContentAccessRequest,
) -> Response[HTTPValidationError | SessionContentAccessRequestSummary]:
    """Create My Session Content Access Request

     Request content access to a known session in the caller's organization.

    Returns the existing request on repeated submissions while pending. No
    findings grant is required. Missing, foreign, or scrubbed sessions return
    404; already-readable content returns 409. Credentials must identify a user.

    Args:
        body (CreateSessionContentAccessRequest): Request content access to a known session;
            identity comes from authentication.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | SessionContentAccessRequestSummary]
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
    body: CreateSessionContentAccessRequest,
) -> HTTPValidationError | SessionContentAccessRequestSummary | None:
    """Create My Session Content Access Request

     Request content access to a known session in the caller's organization.

    Returns the existing request on repeated submissions while pending. No
    findings grant is required. Missing, foreign, or scrubbed sessions return
    404; already-readable content returns 409. Credentials must identify a user.

    Args:
        body (CreateSessionContentAccessRequest): Request content access to a known session;
            identity comes from authentication.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | SessionContentAccessRequestSummary
    """

    return sync_detailed(
        client=client,
        body=body,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient | Client,
    body: CreateSessionContentAccessRequest,
) -> Response[HTTPValidationError | SessionContentAccessRequestSummary]:
    """Create My Session Content Access Request

     Request content access to a known session in the caller's organization.

    Returns the existing request on repeated submissions while pending. No
    findings grant is required. Missing, foreign, or scrubbed sessions return
    404; already-readable content returns 409. Credentials must identify a user.

    Args:
        body (CreateSessionContentAccessRequest): Request content access to a known session;
            identity comes from authentication.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | SessionContentAccessRequestSummary]
    """

    kwargs = _get_kwargs(
        body=body,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient | Client,
    body: CreateSessionContentAccessRequest,
) -> HTTPValidationError | SessionContentAccessRequestSummary | None:
    """Create My Session Content Access Request

     Request content access to a known session in the caller's organization.

    Returns the existing request on repeated submissions while pending. No
    findings grant is required. Missing, foreign, or scrubbed sessions return
    404; already-readable content returns 409. Credentials must identify a user.

    Args:
        body (CreateSessionContentAccessRequest): Request content access to a known session;
            identity comes from authentication.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | SessionContentAccessRequestSummary
    """

    return (
        await asyncio_detailed(
            client=client,
            body=body,
        )
    ).parsed
