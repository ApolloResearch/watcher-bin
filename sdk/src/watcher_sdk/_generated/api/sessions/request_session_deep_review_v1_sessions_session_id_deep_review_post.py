from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.deep_review_request_response import DeepReviewRequestResponse
from ...models.http_validation_error import HTTPValidationError
from ...types import Response


def _get_kwargs(
    session_id: str,
) -> dict[str, Any]:

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/v1/sessions/{session_id}/deep-review".format(
            session_id=quote(str(session_id), safe=""),
        ),
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Any | DeepReviewRequestResponse | HTTPValidationError | None:
    if response.status_code == 202:
        response_202 = DeepReviewRequestResponse.from_dict(response.json())

        return response_202

    if response.status_code == 409:
        response_409 = cast(Any, None)
        return response_409

    if response.status_code == 422:
        response_422 = HTTPValidationError.from_dict(response.json())

        return response_422

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Response[Any | DeepReviewRequestResponse | HTTPValidationError]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    session_id: str,
    *,
    client: AuthenticatedClient | Client,
) -> Response[Any | DeepReviewRequestResponse | HTTPValidationError]:
    """Request Session Deep Review

     Queue a deep review of the session's latest transcript, or return the one already queued.

    Requires ownership or ``sessions:grade:any``, without requiring content access.
    Repeating the request for an unchanged transcript returns the same operation.
    If that review failed, a fresh attempt is queued. 402 when the organization
    is over its monthly grading cap.

    Args:
        session_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | DeepReviewRequestResponse | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        session_id=session_id,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    session_id: str,
    *,
    client: AuthenticatedClient | Client,
) -> Any | DeepReviewRequestResponse | HTTPValidationError | None:
    """Request Session Deep Review

     Queue a deep review of the session's latest transcript, or return the one already queued.

    Requires ownership or ``sessions:grade:any``, without requiring content access.
    Repeating the request for an unchanged transcript returns the same operation.
    If that review failed, a fresh attempt is queued. 402 when the organization
    is over its monthly grading cap.

    Args:
        session_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | DeepReviewRequestResponse | HTTPValidationError
    """

    return sync_detailed(
        session_id=session_id,
        client=client,
    ).parsed


async def asyncio_detailed(
    session_id: str,
    *,
    client: AuthenticatedClient | Client,
) -> Response[Any | DeepReviewRequestResponse | HTTPValidationError]:
    """Request Session Deep Review

     Queue a deep review of the session's latest transcript, or return the one already queued.

    Requires ownership or ``sessions:grade:any``, without requiring content access.
    Repeating the request for an unchanged transcript returns the same operation.
    If that review failed, a fresh attempt is queued. 402 when the organization
    is over its monthly grading cap.

    Args:
        session_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | DeepReviewRequestResponse | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        session_id=session_id,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    session_id: str,
    *,
    client: AuthenticatedClient | Client,
) -> Any | DeepReviewRequestResponse | HTTPValidationError | None:
    """Request Session Deep Review

     Queue a deep review of the session's latest transcript, or return the one already queued.

    Requires ownership or ``sessions:grade:any``, without requiring content access.
    Repeating the request for an unchanged transcript returns the same operation.
    If that review failed, a fresh attempt is queued. 402 when the organization
    is over its monthly grading cap.

    Args:
        session_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | DeepReviewRequestResponse | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            session_id=session_id,
            client=client,
        )
    ).parsed
