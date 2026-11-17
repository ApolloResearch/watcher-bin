from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.session_content_access_request_pending_count import (
    SessionContentAccessRequestPendingCount,
)
from ...types import Response


def _get_kwargs() -> dict[str, Any]:

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/v1/session-content-access-requests/pending-count",
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> SessionContentAccessRequestPendingCount | None:
    if response.status_code == 200:
        response_200 = SessionContentAccessRequestPendingCount.from_dict(
            response.json()
        )

        return response_200

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Response[SessionContentAccessRequestPendingCount]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient | Client,
) -> Response[SessionContentAccessRequestPendingCount]:
    """Count Pending Session Content Access Requests

     Count requests in the current organization that await review.

    Requires ``sessions:access-requests:review``, included in the admin role.
    The Analyzer polls this for its navigation badge. It returns no requester
    identities or session ids, so unlike the list it is not admin-audited:
    auditing a background poll would record reviews that never happened.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[SessionContentAccessRequestPendingCount]
    """

    kwargs = _get_kwargs()

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient | Client,
) -> SessionContentAccessRequestPendingCount | None:
    """Count Pending Session Content Access Requests

     Count requests in the current organization that await review.

    Requires ``sessions:access-requests:review``, included in the admin role.
    The Analyzer polls this for its navigation badge. It returns no requester
    identities or session ids, so unlike the list it is not admin-audited:
    auditing a background poll would record reviews that never happened.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        SessionContentAccessRequestPendingCount
    """

    return sync_detailed(
        client=client,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient | Client,
) -> Response[SessionContentAccessRequestPendingCount]:
    """Count Pending Session Content Access Requests

     Count requests in the current organization that await review.

    Requires ``sessions:access-requests:review``, included in the admin role.
    The Analyzer polls this for its navigation badge. It returns no requester
    identities or session ids, so unlike the list it is not admin-audited:
    auditing a background poll would record reviews that never happened.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[SessionContentAccessRequestPendingCount]
    """

    kwargs = _get_kwargs()

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient | Client,
) -> SessionContentAccessRequestPendingCount | None:
    """Count Pending Session Content Access Requests

     Count requests in the current organization that await review.

    Requires ``sessions:access-requests:review``, included in the admin role.
    The Analyzer polls this for its navigation badge. It returns no requester
    identities or session ids, so unlike the list it is not admin-audited:
    auditing a background poll would record reviews that never happened.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        SessionContentAccessRequestPendingCount
    """

    return (
        await asyncio_detailed(
            client=client,
        )
    ).parsed
