from http import HTTPStatus
from typing import Any
from urllib.parse import quote
from uuid import UUID

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.review_session_content_access_request import (
    ReviewSessionContentAccessRequest,
)
from ...models.session_content_access_request_summary import (
    SessionContentAccessRequestSummary,
)
from ...types import Response


def _get_kwargs(
    request_id: UUID,
    *,
    body: ReviewSessionContentAccessRequest,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

    _kwargs: dict[str, Any] = {
        "method": "patch",
        "url": "/v1/session-content-access-requests/{request_id}".format(
            request_id=quote(str(request_id), safe=""),
        ),
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
    request_id: UUID,
    *,
    client: AuthenticatedClient | Client,
    body: ReviewSessionContentAccessRequest,
) -> Response[HTTPValidationError | SessionContentAccessRequestSummary]:
    """Review Session Content Access Request Endpoint

     Approve or deny a pending request, including your own.

    Requires ``sessions:access-requests:review`` and a signed-in user identity.
    Approval lasts eight hours unless a shorter, timezone-aware ``valid_until``
    is supplied. Expiries must be in the future and at most eight hours after
    review (422). A completed decision cannot be changed (409). Missing or
    foreign requests return 404; scrubbed content cannot be approved (409).

    Args:
        request_id (UUID):
        body (ReviewSessionContentAccessRequest): A final decision; approvals default to eight
            hours and may use a shorter expiry.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | SessionContentAccessRequestSummary]
    """

    kwargs = _get_kwargs(
        request_id=request_id,
        body=body,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    request_id: UUID,
    *,
    client: AuthenticatedClient | Client,
    body: ReviewSessionContentAccessRequest,
) -> HTTPValidationError | SessionContentAccessRequestSummary | None:
    """Review Session Content Access Request Endpoint

     Approve or deny a pending request, including your own.

    Requires ``sessions:access-requests:review`` and a signed-in user identity.
    Approval lasts eight hours unless a shorter, timezone-aware ``valid_until``
    is supplied. Expiries must be in the future and at most eight hours after
    review (422). A completed decision cannot be changed (409). Missing or
    foreign requests return 404; scrubbed content cannot be approved (409).

    Args:
        request_id (UUID):
        body (ReviewSessionContentAccessRequest): A final decision; approvals default to eight
            hours and may use a shorter expiry.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | SessionContentAccessRequestSummary
    """

    return sync_detailed(
        request_id=request_id,
        client=client,
        body=body,
    ).parsed


async def asyncio_detailed(
    request_id: UUID,
    *,
    client: AuthenticatedClient | Client,
    body: ReviewSessionContentAccessRequest,
) -> Response[HTTPValidationError | SessionContentAccessRequestSummary]:
    """Review Session Content Access Request Endpoint

     Approve or deny a pending request, including your own.

    Requires ``sessions:access-requests:review`` and a signed-in user identity.
    Approval lasts eight hours unless a shorter, timezone-aware ``valid_until``
    is supplied. Expiries must be in the future and at most eight hours after
    review (422). A completed decision cannot be changed (409). Missing or
    foreign requests return 404; scrubbed content cannot be approved (409).

    Args:
        request_id (UUID):
        body (ReviewSessionContentAccessRequest): A final decision; approvals default to eight
            hours and may use a shorter expiry.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | SessionContentAccessRequestSummary]
    """

    kwargs = _get_kwargs(
        request_id=request_id,
        body=body,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    request_id: UUID,
    *,
    client: AuthenticatedClient | Client,
    body: ReviewSessionContentAccessRequest,
) -> HTTPValidationError | SessionContentAccessRequestSummary | None:
    """Review Session Content Access Request Endpoint

     Approve or deny a pending request, including your own.

    Requires ``sessions:access-requests:review`` and a signed-in user identity.
    Approval lasts eight hours unless a shorter, timezone-aware ``valid_until``
    is supplied. Expiries must be in the future and at most eight hours after
    review (422). A completed decision cannot be changed (409). Missing or
    foreign requests return 404; scrubbed content cannot be approved (409).

    Args:
        request_id (UUID):
        body (ReviewSessionContentAccessRequest): A final decision; approvals default to eight
            hours and may use a shorter expiry.

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
            body=body,
        )
    ).parsed
