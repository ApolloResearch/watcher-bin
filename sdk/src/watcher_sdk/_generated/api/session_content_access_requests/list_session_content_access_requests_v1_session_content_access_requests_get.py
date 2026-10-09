from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.admin_session_content_access_request_list_response import (
    AdminSessionContentAccessRequestListResponse,
)
from ...models.http_validation_error import HTTPValidationError
from ...models.session_content_access_request_status import (
    SessionContentAccessRequestStatus,
)
from ...models.session_content_access_request_view import (
    SessionContentAccessRequestView,
)
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    status: list[SessionContentAccessRequestStatus] | None | Unset = UNSET,
    view: None | SessionContentAccessRequestView | Unset = UNSET,
    limit: int | Unset = 20,
    offset: int | Unset = 0,
) -> dict[str, Any]:

    params: dict[str, Any] = {}

    json_status: list[str] | None | Unset
    if isinstance(status, Unset):
        json_status = UNSET
    elif isinstance(status, list):
        json_status = []
        for status_type_0_item_data in status:
            status_type_0_item = status_type_0_item_data.value
            json_status.append(status_type_0_item)

    else:
        json_status = status
    params["status"] = json_status

    json_view: None | str | Unset
    if isinstance(view, Unset):
        json_view = UNSET
    elif isinstance(view, SessionContentAccessRequestView):
        json_view = view.value
    else:
        json_view = view
    params["view"] = json_view

    params["limit"] = limit

    params["offset"] = offset

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/v1/session-content-access-requests",
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> AdminSessionContentAccessRequestListResponse | HTTPValidationError | None:
    if response.status_code == 200:
        response_200 = AdminSessionContentAccessRequestListResponse.from_dict(
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
) -> Response[AdminSessionContentAccessRequestListResponse | HTTPValidationError]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient | Client,
    status: list[SessionContentAccessRequestStatus] | None | Unset = UNSET,
    view: None | SessionContentAccessRequestView | Unset = UNSET,
    limit: int | Unset = 20,
    offset: int | Unset = 0,
) -> Response[AdminSessionContentAccessRequestListResponse | HTTPValidationError]:
    """List Session Content Access Requests

     List requests from all users in the current organization, newest first.

    Requires ``sessions:access-requests:review``, included in the admin role.
    Repeat ``status`` to include multiple decisions. Approved results include
    expired approvals. ``view`` selects pending requests, active approvals, or
    historical (denied, revoked or expired) requests using database time. Filters combine;
    pending/active counts always cover the organization. Identities are included, never content.

    Args:
        status (list[SessionContentAccessRequestStatus] | None | Unset):
        view (None | SessionContentAccessRequestView | Unset):
        limit (int | Unset):  Default: 20.
        offset (int | Unset):  Default: 0.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[AdminSessionContentAccessRequestListResponse | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        status=status,
        view=view,
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
    status: list[SessionContentAccessRequestStatus] | None | Unset = UNSET,
    view: None | SessionContentAccessRequestView | Unset = UNSET,
    limit: int | Unset = 20,
    offset: int | Unset = 0,
) -> AdminSessionContentAccessRequestListResponse | HTTPValidationError | None:
    """List Session Content Access Requests

     List requests from all users in the current organization, newest first.

    Requires ``sessions:access-requests:review``, included in the admin role.
    Repeat ``status`` to include multiple decisions. Approved results include
    expired approvals. ``view`` selects pending requests, active approvals, or
    historical (denied, revoked or expired) requests using database time. Filters combine;
    pending/active counts always cover the organization. Identities are included, never content.

    Args:
        status (list[SessionContentAccessRequestStatus] | None | Unset):
        view (None | SessionContentAccessRequestView | Unset):
        limit (int | Unset):  Default: 20.
        offset (int | Unset):  Default: 0.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        AdminSessionContentAccessRequestListResponse | HTTPValidationError
    """

    return sync_detailed(
        client=client,
        status=status,
        view=view,
        limit=limit,
        offset=offset,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient | Client,
    status: list[SessionContentAccessRequestStatus] | None | Unset = UNSET,
    view: None | SessionContentAccessRequestView | Unset = UNSET,
    limit: int | Unset = 20,
    offset: int | Unset = 0,
) -> Response[AdminSessionContentAccessRequestListResponse | HTTPValidationError]:
    """List Session Content Access Requests

     List requests from all users in the current organization, newest first.

    Requires ``sessions:access-requests:review``, included in the admin role.
    Repeat ``status`` to include multiple decisions. Approved results include
    expired approvals. ``view`` selects pending requests, active approvals, or
    historical (denied, revoked or expired) requests using database time. Filters combine;
    pending/active counts always cover the organization. Identities are included, never content.

    Args:
        status (list[SessionContentAccessRequestStatus] | None | Unset):
        view (None | SessionContentAccessRequestView | Unset):
        limit (int | Unset):  Default: 20.
        offset (int | Unset):  Default: 0.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[AdminSessionContentAccessRequestListResponse | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        status=status,
        view=view,
        limit=limit,
        offset=offset,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient | Client,
    status: list[SessionContentAccessRequestStatus] | None | Unset = UNSET,
    view: None | SessionContentAccessRequestView | Unset = UNSET,
    limit: int | Unset = 20,
    offset: int | Unset = 0,
) -> AdminSessionContentAccessRequestListResponse | HTTPValidationError | None:
    """List Session Content Access Requests

     List requests from all users in the current organization, newest first.

    Requires ``sessions:access-requests:review``, included in the admin role.
    Repeat ``status`` to include multiple decisions. Approved results include
    expired approvals. ``view`` selects pending requests, active approvals, or
    historical (denied, revoked or expired) requests using database time. Filters combine;
    pending/active counts always cover the organization. Identities are included, never content.

    Args:
        status (list[SessionContentAccessRequestStatus] | None | Unset):
        view (None | SessionContentAccessRequestView | Unset):
        limit (int | Unset):  Default: 20.
        offset (int | Unset):  Default: 0.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        AdminSessionContentAccessRequestListResponse | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            client=client,
            status=status,
            view=view,
            limit=limit,
            offset=offset,
        )
    ).parsed
