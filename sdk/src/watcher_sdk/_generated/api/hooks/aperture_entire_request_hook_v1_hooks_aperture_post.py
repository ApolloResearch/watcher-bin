from http import HTTPStatus
from typing import Any, cast

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.aperture_hook_accepted import ApertureHookAccepted
from ...models.aperture_hook_request import ApertureHookRequest
from ...models.http_validation_error import HTTPValidationError
from ...types import Response


def _get_kwargs(
    *,
    body: ApertureHookRequest,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/v1/hooks/aperture",
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Any | ApertureHookAccepted | HTTPValidationError | None:
    if response.status_code == 202:
        response_202 = ApertureHookAccepted.from_dict(response.json())

        return response_202

    if response.status_code == 403:
        response_403 = cast(Any, None)
        return response_403

    if response.status_code == 413:
        response_413 = cast(Any, None)
        return response_413

    if response.status_code == 422:
        response_422 = HTTPValidationError.from_dict(response.json())

        return response_422

    if response.status_code == 503:
        response_503 = cast(Any, None)
        return response_503

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Response[Any | ApertureHookAccepted | HTTPValidationError]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient | Client,
    body: ApertureHookRequest,
) -> Response[Any | ApertureHookAccepted | HTTPValidationError]:
    r"""Aperture Entire Request Hook

     Accept a supported coding-agent request/response capture from Tailscale Aperture for asynchronous
    monitoring.

    Configure Aperture with events=[\"entire_request\"] and
    send=[\"request_body\", \"response_body\"]. The API key must have
    sessions:write:any so metadata.login_name can attribute the session.
    Admin enforcement.mode selects observation or ingestion only (paused);
    this asynchronous transport always caps enforcement at observe. Only tool
    calls in the response are evaluated. Text-only turns are ingested too.

    A 202 confirms admission, not completed grading or durable storage.
    Unsupported formats and malformed provider bodies are logged after the
    ACK. Captures require recognized coding-harness identity, using the
    per-format markers documented in the hooks reference. Other applications
    are skipped.

    Args:
        body (ApertureHookRequest): The fixed webhook envelope with both required send types
            enabled.

            Raw request and reconstructed response objects are forwarded to the selected
            format parser. A null or absent response represents an upstream call that
            produced no response body and is skipped: Aperture omits ``response_body``
            when the client disconnects before the provider answers (capture status 0).
            Extra metadata and send types are ignored.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | ApertureHookAccepted | HTTPValidationError]
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
    body: ApertureHookRequest,
) -> Any | ApertureHookAccepted | HTTPValidationError | None:
    r"""Aperture Entire Request Hook

     Accept a supported coding-agent request/response capture from Tailscale Aperture for asynchronous
    monitoring.

    Configure Aperture with events=[\"entire_request\"] and
    send=[\"request_body\", \"response_body\"]. The API key must have
    sessions:write:any so metadata.login_name can attribute the session.
    Admin enforcement.mode selects observation or ingestion only (paused);
    this asynchronous transport always caps enforcement at observe. Only tool
    calls in the response are evaluated. Text-only turns are ingested too.

    A 202 confirms admission, not completed grading or durable storage.
    Unsupported formats and malformed provider bodies are logged after the
    ACK. Captures require recognized coding-harness identity, using the
    per-format markers documented in the hooks reference. Other applications
    are skipped.

    Args:
        body (ApertureHookRequest): The fixed webhook envelope with both required send types
            enabled.

            Raw request and reconstructed response objects are forwarded to the selected
            format parser. A null or absent response represents an upstream call that
            produced no response body and is skipped: Aperture omits ``response_body``
            when the client disconnects before the provider answers (capture status 0).
            Extra metadata and send types are ignored.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | ApertureHookAccepted | HTTPValidationError
    """

    return sync_detailed(
        client=client,
        body=body,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient | Client,
    body: ApertureHookRequest,
) -> Response[Any | ApertureHookAccepted | HTTPValidationError]:
    r"""Aperture Entire Request Hook

     Accept a supported coding-agent request/response capture from Tailscale Aperture for asynchronous
    monitoring.

    Configure Aperture with events=[\"entire_request\"] and
    send=[\"request_body\", \"response_body\"]. The API key must have
    sessions:write:any so metadata.login_name can attribute the session.
    Admin enforcement.mode selects observation or ingestion only (paused);
    this asynchronous transport always caps enforcement at observe. Only tool
    calls in the response are evaluated. Text-only turns are ingested too.

    A 202 confirms admission, not completed grading or durable storage.
    Unsupported formats and malformed provider bodies are logged after the
    ACK. Captures require recognized coding-harness identity, using the
    per-format markers documented in the hooks reference. Other applications
    are skipped.

    Args:
        body (ApertureHookRequest): The fixed webhook envelope with both required send types
            enabled.

            Raw request and reconstructed response objects are forwarded to the selected
            format parser. A null or absent response represents an upstream call that
            produced no response body and is skipped: Aperture omits ``response_body``
            when the client disconnects before the provider answers (capture status 0).
            Extra metadata and send types are ignored.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | ApertureHookAccepted | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        body=body,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient | Client,
    body: ApertureHookRequest,
) -> Any | ApertureHookAccepted | HTTPValidationError | None:
    r"""Aperture Entire Request Hook

     Accept a supported coding-agent request/response capture from Tailscale Aperture for asynchronous
    monitoring.

    Configure Aperture with events=[\"entire_request\"] and
    send=[\"request_body\", \"response_body\"]. The API key must have
    sessions:write:any so metadata.login_name can attribute the session.
    Admin enforcement.mode selects observation or ingestion only (paused);
    this asynchronous transport always caps enforcement at observe. Only tool
    calls in the response are evaluated. Text-only turns are ingested too.

    A 202 confirms admission, not completed grading or durable storage.
    Unsupported formats and malformed provider bodies are logged after the
    ACK. Captures require recognized coding-harness identity, using the
    per-format markers documented in the hooks reference. Other applications
    are skipped.

    Args:
        body (ApertureHookRequest): The fixed webhook envelope with both required send types
            enabled.

            Raw request and reconstructed response objects are forwarded to the selected
            format parser. A null or absent response represents an upstream call that
            produced no response body and is skipped: Aperture omits ``response_body``
            when the client disconnects before the provider answers (capture status 0).
            Extra metadata and send types are ignored.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | ApertureHookAccepted | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            client=client,
            body=body,
        )
    ).parsed
