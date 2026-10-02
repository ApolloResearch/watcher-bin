from http import HTTPStatus
from typing import Any
from urllib.parse import quote
from uuid import UUID

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.deep_review_request_response import DeepReviewRequestResponse
from ...models.http_validation_error import HTTPValidationError
from ...types import Response


def _get_kwargs(
    session_id: str,
    operation_id: UUID,
) -> dict[str, Any]:

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/v1/sessions/{session_id}/deep-review/{operation_id}".format(
            session_id=quote(str(session_id), safe=""),
            operation_id=quote(str(operation_id), safe=""),
        ),
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> DeepReviewRequestResponse | HTTPValidationError | None:
    if response.status_code == 200:
        response_200 = DeepReviewRequestResponse.from_dict(response.json())

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
) -> Response[DeepReviewRequestResponse | HTTPValidationError]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    session_id: str,
    operation_id: UUID,
    *,
    client: AuthenticatedClient | Client,
) -> Response[DeepReviewRequestResponse | HTTPValidationError]:
    """Get Session Deep Review Request

     Poll one on-demand deep review; 404 if it is not this session's review or the session is not
    visible.

    Args:
        session_id (str):
        operation_id (UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[DeepReviewRequestResponse | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        session_id=session_id,
        operation_id=operation_id,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    session_id: str,
    operation_id: UUID,
    *,
    client: AuthenticatedClient | Client,
) -> DeepReviewRequestResponse | HTTPValidationError | None:
    """Get Session Deep Review Request

     Poll one on-demand deep review; 404 if it is not this session's review or the session is not
    visible.

    Args:
        session_id (str):
        operation_id (UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        DeepReviewRequestResponse | HTTPValidationError
    """

    return sync_detailed(
        session_id=session_id,
        operation_id=operation_id,
        client=client,
    ).parsed


async def asyncio_detailed(
    session_id: str,
    operation_id: UUID,
    *,
    client: AuthenticatedClient | Client,
) -> Response[DeepReviewRequestResponse | HTTPValidationError]:
    """Get Session Deep Review Request

     Poll one on-demand deep review; 404 if it is not this session's review or the session is not
    visible.

    Args:
        session_id (str):
        operation_id (UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[DeepReviewRequestResponse | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        session_id=session_id,
        operation_id=operation_id,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    session_id: str,
    operation_id: UUID,
    *,
    client: AuthenticatedClient | Client,
) -> DeepReviewRequestResponse | HTTPValidationError | None:
    """Get Session Deep Review Request

     Poll one on-demand deep review; 404 if it is not this session's review or the session is not
    visible.

    Args:
        session_id (str):
        operation_id (UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        DeepReviewRequestResponse | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            session_id=session_id,
            operation_id=operation_id,
            client=client,
        )
    ).parsed
