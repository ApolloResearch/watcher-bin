from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.aperture_pre_response_request import AperturePreResponseRequest
from ...models.aperture_pre_response_response import AperturePreResponseResponse
from ...models.http_validation_error import HTTPValidationError
from ...types import Response


def _get_kwargs(
    *,
    body: AperturePreResponseRequest,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/v1/hooks/aperture/pre-response",
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> AperturePreResponseResponse | HTTPValidationError | None:
    if response.status_code == 200:
        response_200 = AperturePreResponseResponse.from_dict(response.json())

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
) -> Response[AperturePreResponseResponse | HTTPValidationError]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient | Client,
    body: AperturePreResponseRequest,
) -> Response[AperturePreResponseResponse | HTTPValidationError]:
    """Aperture Pre Response Hook

     Evaluate Aperture's pending tool calls before the gateway releases them.

    Configure a blocking tool_call_pre_response hook sending request_body,
    response_body and tools, with fail_policy="fail_closed" and a timeout exceeding
    300 seconds. The authenticated caller requires sessions:write:any; Aperture
    metadata attributes the captured conversation to its developer. The server
    applies the organization's existing enforcement and grading-failure policy.
    Denied shell calls become harmless notice commands. Other denied tools
    block the pending callback. There is no resampling or tool-name replacement.
    Refused calls are recorded before responding; allowed calls record asynchronously.

    Args:
        body (AperturePreResponseRequest): Blocking callback with original context and the exact
            calls awaiting release.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[AperturePreResponseResponse | HTTPValidationError]
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
    body: AperturePreResponseRequest,
) -> AperturePreResponseResponse | HTTPValidationError | None:
    """Aperture Pre Response Hook

     Evaluate Aperture's pending tool calls before the gateway releases them.

    Configure a blocking tool_call_pre_response hook sending request_body,
    response_body and tools, with fail_policy="fail_closed" and a timeout exceeding
    300 seconds. The authenticated caller requires sessions:write:any; Aperture
    metadata attributes the captured conversation to its developer. The server
    applies the organization's existing enforcement and grading-failure policy.
    Denied shell calls become harmless notice commands. Other denied tools
    block the pending callback. There is no resampling or tool-name replacement.
    Refused calls are recorded before responding; allowed calls record asynchronously.

    Args:
        body (AperturePreResponseRequest): Blocking callback with original context and the exact
            calls awaiting release.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        AperturePreResponseResponse | HTTPValidationError
    """

    return sync_detailed(
        client=client,
        body=body,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient | Client,
    body: AperturePreResponseRequest,
) -> Response[AperturePreResponseResponse | HTTPValidationError]:
    """Aperture Pre Response Hook

     Evaluate Aperture's pending tool calls before the gateway releases them.

    Configure a blocking tool_call_pre_response hook sending request_body,
    response_body and tools, with fail_policy="fail_closed" and a timeout exceeding
    300 seconds. The authenticated caller requires sessions:write:any; Aperture
    metadata attributes the captured conversation to its developer. The server
    applies the organization's existing enforcement and grading-failure policy.
    Denied shell calls become harmless notice commands. Other denied tools
    block the pending callback. There is no resampling or tool-name replacement.
    Refused calls are recorded before responding; allowed calls record asynchronously.

    Args:
        body (AperturePreResponseRequest): Blocking callback with original context and the exact
            calls awaiting release.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[AperturePreResponseResponse | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        body=body,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient | Client,
    body: AperturePreResponseRequest,
) -> AperturePreResponseResponse | HTTPValidationError | None:
    """Aperture Pre Response Hook

     Evaluate Aperture's pending tool calls before the gateway releases them.

    Configure a blocking tool_call_pre_response hook sending request_body,
    response_body and tools, with fail_policy="fail_closed" and a timeout exceeding
    300 seconds. The authenticated caller requires sessions:write:any; Aperture
    metadata attributes the captured conversation to its developer. The server
    applies the organization's existing enforcement and grading-failure policy.
    Denied shell calls become harmless notice commands. Other denied tools
    block the pending callback. There is no resampling or tool-name replacement.
    Refused calls are recorded before responding; allowed calls record asynchronously.

    Args:
        body (AperturePreResponseRequest): Blocking callback with original context and the exact
            calls awaiting release.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        AperturePreResponseResponse | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            client=client,
            body=body,
        )
    ).parsed
