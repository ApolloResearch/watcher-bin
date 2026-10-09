from http import HTTPStatus
from typing import Any
from uuid import UUID

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.session_content_access_request_list_response import (
    SessionContentAccessRequestListResponse,
)
from ...models.session_content_access_request_status import (
    SessionContentAccessRequestStatus,
)
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    session_id: None | Unset | UUID = UNSET,
    status: None | SessionContentAccessRequestStatus | Unset = UNSET,
    active_only: bool | Unset = False,
    limit: int | Unset = 20,
    offset: int | Unset = 0,
) -> dict[str, Any]:

    params: dict[str, Any] = {}

    json_session_id: None | str | Unset
    if isinstance(session_id, Unset):
        json_session_id = UNSET
    elif isinstance(session_id, UUID):
        json_session_id = str(session_id)
    else:
        json_session_id = session_id
    params["session_id"] = json_session_id

    json_status: None | str | Unset
    if isinstance(status, Unset):
        json_status = UNSET
    elif isinstance(status, SessionContentAccessRequestStatus):
        json_status = status.value
    else:
        json_status = status
    params["status"] = json_status

    params["active_only"] = active_only

    params["limit"] = limit

    params["offset"] = offset

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/v1/users/me/session-content-access-requests",
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> HTTPValidationError | SessionContentAccessRequestListResponse | None:
    if response.status_code == 200:
        response_200 = SessionContentAccessRequestListResponse.from_dict(
            response.json()
        )

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
) -> Response[HTTPValidationError | SessionContentAccessRequestListResponse]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient | Client,
    session_id: None | Unset | UUID = UNSET,
    status: None | SessionContentAccessRequestStatus | Unset = UNSET,
    active_only: bool | Unset = False,
    limit: int | Unset = 20,
    offset: int | Unset = 0,
) -> Response[HTTPValidationError | SessionContentAccessRequestListResponse]:
    """List My Session Content Access Requests

     List only the signed-in user's access requests in their current organization.

    Admins also receive only their own requests. No session-read permission is
    required. Service credentials without a user identity receive HTTP 401.
    Results are newest first; status filters use the stored review decision,
    so approved requests include those whose ``valid_until`` has passed.
    ``active_only`` limits results to pending requests and currently valid approvals.

    Args:
        session_id (None | Unset | UUID):
        status (None | SessionContentAccessRequestStatus | Unset):
        active_only (bool | Unset):  Default: False.
        limit (int | Unset):  Default: 20.
        offset (int | Unset):  Default: 0.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | SessionContentAccessRequestListResponse]
    """

    kwargs = _get_kwargs(
        session_id=session_id,
        status=status,
        active_only=active_only,
        limit=limit,
        offset=offset,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient | Client,
    session_id: None | Unset | UUID = UNSET,
    status: None | SessionContentAccessRequestStatus | Unset = UNSET,
    active_only: bool | Unset = False,
    limit: int | Unset = 20,
    offset: int | Unset = 0,
) -> HTTPValidationError | SessionContentAccessRequestListResponse | None:
    """List My Session Content Access Requests

     List only the signed-in user's access requests in their current organization.

    Admins also receive only their own requests. No session-read permission is
    required. Service credentials without a user identity receive HTTP 401.
    Results are newest first; status filters use the stored review decision,
    so approved requests include those whose ``valid_until`` has passed.
    ``active_only`` limits results to pending requests and currently valid approvals.

    Args:
        session_id (None | Unset | UUID):
        status (None | SessionContentAccessRequestStatus | Unset):
        active_only (bool | Unset):  Default: False.
        limit (int | Unset):  Default: 20.
        offset (int | Unset):  Default: 0.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | SessionContentAccessRequestListResponse
    """

    return sync_detailed(
        client=client,
        session_id=session_id,
        status=status,
        active_only=active_only,
        limit=limit,
        offset=offset,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient | Client,
    session_id: None | Unset | UUID = UNSET,
    status: None | SessionContentAccessRequestStatus | Unset = UNSET,
    active_only: bool | Unset = False,
    limit: int | Unset = 20,
    offset: int | Unset = 0,
) -> Response[HTTPValidationError | SessionContentAccessRequestListResponse]:
    """List My Session Content Access Requests

     List only the signed-in user's access requests in their current organization.

    Admins also receive only their own requests. No session-read permission is
    required. Service credentials without a user identity receive HTTP 401.
    Results are newest first; status filters use the stored review decision,
    so approved requests include those whose ``valid_until`` has passed.
    ``active_only`` limits results to pending requests and currently valid approvals.

    Args:
        session_id (None | Unset | UUID):
        status (None | SessionContentAccessRequestStatus | Unset):
        active_only (bool | Unset):  Default: False.
        limit (int | Unset):  Default: 20.
        offset (int | Unset):  Default: 0.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | SessionContentAccessRequestListResponse]
    """

    kwargs = _get_kwargs(
        session_id=session_id,
        status=status,
        active_only=active_only,
        limit=limit,
        offset=offset,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient | Client,
    session_id: None | Unset | UUID = UNSET,
    status: None | SessionContentAccessRequestStatus | Unset = UNSET,
    active_only: bool | Unset = False,
    limit: int | Unset = 20,
    offset: int | Unset = 0,
) -> HTTPValidationError | SessionContentAccessRequestListResponse | None:
    """List My Session Content Access Requests

     List only the signed-in user's access requests in their current organization.

    Admins also receive only their own requests. No session-read permission is
    required. Service credentials without a user identity receive HTTP 401.
    Results are newest first; status filters use the stored review decision,
    so approved requests include those whose ``valid_until`` has passed.
    ``active_only`` limits results to pending requests and currently valid approvals.

    Args:
        session_id (None | Unset | UUID):
        status (None | SessionContentAccessRequestStatus | Unset):
        active_only (bool | Unset):  Default: False.
        limit (int | Unset):  Default: 20.
        offset (int | Unset):  Default: 0.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | SessionContentAccessRequestListResponse
    """

    return (
        await asyncio_detailed(
            client=client,
            session_id=session_id,
            status=status,
            active_only=active_only,
            limit=limit,
            offset=offset,
        )
    ).parsed
