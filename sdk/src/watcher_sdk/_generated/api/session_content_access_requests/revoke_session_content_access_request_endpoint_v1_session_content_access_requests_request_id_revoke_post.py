from http import HTTPStatus
from typing import Any
from urllib.parse import quote
from uuid import UUID

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.session_content_access_request_summary import (
    SessionContentAccessRequestSummary,
)
from ...types import Response


def _get_kwargs(
    request_id: UUID,
) -> dict[str, Any]:

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/v1/session-content-access-requests/{request_id}/revoke".format(
            request_id=quote(str(request_id), safe=""),
        ),
    }

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
    request_id: UUID,
    *,
    client: AuthenticatedClient | Client,
) -> Response[HTTPValidationError | SessionContentAccessRequestSummary]:
    """Revoke Session Content Access Request Endpoint

     Revoke an active approval, preserving its original review and expiry.

    Requires ``sessions:access-requests:review`` and a signed-in user identity.
    Missing or foreign requests return 404. Pending, denied, expired, or already
    revoked requests return 409. The server records the revoker and revocation time.

    Args:
        request_id (UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | SessionContentAccessRequestSummary]
    """

    kwargs = _get_kwargs(
        request_id=request_id,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    request_id: UUID,
    *,
    client: AuthenticatedClient | Client,
) -> HTTPValidationError | SessionContentAccessRequestSummary | None:
    """Revoke Session Content Access Request Endpoint

     Revoke an active approval, preserving its original review and expiry.

    Requires ``sessions:access-requests:review`` and a signed-in user identity.
    Missing or foreign requests return 404. Pending, denied, expired, or already
    revoked requests return 409. The server records the revoker and revocation time.

    Args:
        request_id (UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | SessionContentAccessRequestSummary
    """

    return sync_detailed(
        request_id=request_id,
        client=client,
    ).parsed


async def asyncio_detailed(
    request_id: UUID,
    *,
    client: AuthenticatedClient | Client,
) -> Response[HTTPValidationError | SessionContentAccessRequestSummary]:
    """Revoke Session Content Access Request Endpoint

     Revoke an active approval, preserving its original review and expiry.

    Requires ``sessions:access-requests:review`` and a signed-in user identity.
    Missing or foreign requests return 404. Pending, denied, expired, or already
    revoked requests return 409. The server records the revoker and revocation time.

    Args:
        request_id (UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | SessionContentAccessRequestSummary]
    """

    kwargs = _get_kwargs(
        request_id=request_id,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    request_id: UUID,
    *,
    client: AuthenticatedClient | Client,
) -> HTTPValidationError | SessionContentAccessRequestSummary | None:
    """Revoke Session Content Access Request Endpoint

     Revoke an active approval, preserving its original review and expiry.

    Requires ``sessions:access-requests:review`` and a signed-in user identity.
    Missing or foreign requests return 404. Pending, denied, expired, or already
    revoked requests return 409. The server records the revoker and revocation time.

    Args:
        request_id (UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | SessionContentAccessRequestSummary
    """

    return (
        await asyncio_detailed(
            request_id=request_id,
            client=client,
        )
    ).parsed
