from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.grader_detail import GraderDetail
from ...models.http_validation_error import HTTPValidationError
from ...models.update_grader_request import UpdateGraderRequest
from ...types import Response


def _get_kwargs(
    grader_id: str,
    *,
    body: UpdateGraderRequest,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

    _kwargs: dict[str, Any] = {
        "method": "patch",
        "url": "/v1/graders/{grader_id}".format(
            grader_id=quote(str(grader_id), safe=""),
        ),
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> GraderDetail | HTTPValidationError | None:
    if response.status_code == 200:
        response_200 = GraderDetail.from_dict(response.json())

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
) -> Response[GraderDetail | HTTPValidationError]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    grader_id: str,
    *,
    client: AuthenticatedClient | Client,
    body: UpdateGraderRequest,
) -> Response[GraderDetail | HTTPValidationError]:
    """Update Grader Endpoint

     Create a new version of a visible grader with the supplied updates.

    Updating a visible grader requires ownership (403 otherwise). Built-in
    graders are immutable (403); missing, inaccessible or archived graders return 404.

    Args:
        grader_id (str):
        body (UpdateGraderRequest): Request body for PATCH /v1/graders/{grader_id}.

            PATCH creates a new grader version instead of mutating. All fields are optional;
            only fields present in the request JSON are merged into the new version.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[GraderDetail | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        grader_id=grader_id,
        body=body,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    grader_id: str,
    *,
    client: AuthenticatedClient | Client,
    body: UpdateGraderRequest,
) -> GraderDetail | HTTPValidationError | None:
    """Update Grader Endpoint

     Create a new version of a visible grader with the supplied updates.

    Updating a visible grader requires ownership (403 otherwise). Built-in
    graders are immutable (403); missing, inaccessible or archived graders return 404.

    Args:
        grader_id (str):
        body (UpdateGraderRequest): Request body for PATCH /v1/graders/{grader_id}.

            PATCH creates a new grader version instead of mutating. All fields are optional;
            only fields present in the request JSON are merged into the new version.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        GraderDetail | HTTPValidationError
    """

    return sync_detailed(
        grader_id=grader_id,
        client=client,
        body=body,
    ).parsed


async def asyncio_detailed(
    grader_id: str,
    *,
    client: AuthenticatedClient | Client,
    body: UpdateGraderRequest,
) -> Response[GraderDetail | HTTPValidationError]:
    """Update Grader Endpoint

     Create a new version of a visible grader with the supplied updates.

    Updating a visible grader requires ownership (403 otherwise). Built-in
    graders are immutable (403); missing, inaccessible or archived graders return 404.

    Args:
        grader_id (str):
        body (UpdateGraderRequest): Request body for PATCH /v1/graders/{grader_id}.

            PATCH creates a new grader version instead of mutating. All fields are optional;
            only fields present in the request JSON are merged into the new version.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[GraderDetail | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        grader_id=grader_id,
        body=body,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    grader_id: str,
    *,
    client: AuthenticatedClient | Client,
    body: UpdateGraderRequest,
) -> GraderDetail | HTTPValidationError | None:
    """Update Grader Endpoint

     Create a new version of a visible grader with the supplied updates.

    Updating a visible grader requires ownership (403 otherwise). Built-in
    graders are immutable (403); missing, inaccessible or archived graders return 404.

    Args:
        grader_id (str):
        body (UpdateGraderRequest): Request body for PATCH /v1/graders/{grader_id}.

            PATCH creates a new grader version instead of mutating. All fields are optional;
            only fields present in the request JSON are merged into the new version.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        GraderDetail | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            grader_id=grader_id,
            client=client,
            body=body,
        )
    ).parsed
