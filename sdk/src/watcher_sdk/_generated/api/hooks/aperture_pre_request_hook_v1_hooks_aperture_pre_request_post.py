from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.aperture_pre_request import AperturePreRequest
from ...models.aperture_pre_request_response import AperturePreRequestResponse
from ...models.http_validation_error import HTTPValidationError
from ...types import Response


def _get_kwargs(
    *,
    body: AperturePreRequest,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/v1/hooks/aperture/pre-request",
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> AperturePreRequestResponse | HTTPValidationError | None:
    if response.status_code == 200:
        response_200 = AperturePreRequestResponse.from_dict(response.json())

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
) -> Response[AperturePreRequestResponse | HTTPValidationError]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient | Client,
    body: AperturePreRequest,
) -> Response[AperturePreRequestResponse | HTTPValidationError]:
    """Aperture Pre Request Hook

     Insert the fixed shell-rewrite notice without grading or policy lookups.

    Configure Aperture's pre_request event with request_body and fail_open.
    This hook is informational; enforcement remains on tool_call_pre_response.

    Args:
        body (AperturePreRequest): Aperture's original provider request before inference.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[AperturePreRequestResponse | HTTPValidationError]
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
    body: AperturePreRequest,
) -> AperturePreRequestResponse | HTTPValidationError | None:
    """Aperture Pre Request Hook

     Insert the fixed shell-rewrite notice without grading or policy lookups.

    Configure Aperture's pre_request event with request_body and fail_open.
    This hook is informational; enforcement remains on tool_call_pre_response.

    Args:
        body (AperturePreRequest): Aperture's original provider request before inference.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        AperturePreRequestResponse | HTTPValidationError
    """

    return sync_detailed(
        client=client,
        body=body,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient | Client,
    body: AperturePreRequest,
) -> Response[AperturePreRequestResponse | HTTPValidationError]:
    """Aperture Pre Request Hook

     Insert the fixed shell-rewrite notice without grading or policy lookups.

    Configure Aperture's pre_request event with request_body and fail_open.
    This hook is informational; enforcement remains on tool_call_pre_response.

    Args:
        body (AperturePreRequest): Aperture's original provider request before inference.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[AperturePreRequestResponse | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        body=body,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient | Client,
    body: AperturePreRequest,
) -> AperturePreRequestResponse | HTTPValidationError | None:
    """Aperture Pre Request Hook

     Insert the fixed shell-rewrite notice without grading or policy lookups.

    Configure Aperture's pre_request event with request_body and fail_open.
    This hook is informational; enforcement remains on tool_call_pre_response.

    Args:
        body (AperturePreRequest): Aperture's original provider request before inference.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        AperturePreRequestResponse | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            client=client,
            body=body,
        )
    ).parsed
