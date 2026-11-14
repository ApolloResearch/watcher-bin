from http import HTTPStatus
from typing import Any, cast

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.aperture_delivery import ApertureDelivery
from ...models.aperture_hook_accepted import ApertureHookAccepted
from ...models.aperture_pre_request_response import AperturePreRequestResponse
from ...models.aperture_pre_response_response import AperturePreResponseResponse
from ...types import Response


def _get_kwargs(
    *,
    body: ApertureDelivery,
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
) -> (
    Any
    | ApertureHookAccepted
    | AperturePreRequestResponse
    | AperturePreResponseResponse
    | None
):
    if response.status_code == 200:

        def _parse_response_200(
            data: object,
        ) -> AperturePreRequestResponse | AperturePreResponseResponse:
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                response_200_type_0 = AperturePreRequestResponse.from_dict(data)

                return response_200_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            if not isinstance(data, dict):
                raise TypeError()
            response_200_type_1 = AperturePreResponseResponse.from_dict(data)

            return response_200_type_1

        response_200 = _parse_response_200(response.json())

        return response_200

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
        response_422 = cast(Any, None)
        return response_422

    if response.status_code == 503:
        response_503 = cast(Any, None)
        return response_503

    if response.status_code == 504:
        response_504 = cast(Any, None)
        return response_504

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Response[
    Any
    | ApertureHookAccepted
    | AperturePreRequestResponse
    | AperturePreResponseResponse
]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient | Client,
    body: ApertureDelivery,
) -> Response[
    Any
    | ApertureHookAccepted
    | AperturePreRequestResponse
    | AperturePreResponseResponse
]:
    """Aperture Hook

     Serve every Tailscale Aperture hook stage from one URL, switching on metadata.stage.

    pre_request adds Watcher's fixed notice to the provider request, without
    grading. pre_response evaluates the pending tool calls before Aperture
    releases them and answers allow, per-call edits (a notice through the
    client's shell tool, or removal) or a block. post_complete, or a delivery
    that names no stage, is observed asynchronously like
    POST /v1/hooks/aperture/entire-request and answered 202. The API key must
    have sessions:write:any so metadata.login_name can attribute the session.

    Configure two Aperture hooks with this URL: one fail_open hook for the
    pre_request and entire_request events, and one tool_call_pre_response hook
    with fail_policy="fail_closed", block_response="message",
    fail_response="message" and a timeout above 300 seconds. Send
    request_body, response_body and tools.

    Args:
        body (ApertureDelivery): Any delivery to Watcher's single Aperture hook URL;
            ``metadata.stage`` says which stage sent it.

            The fields are the union of the three stages' payloads: ``pre_request``
            sends only the request, ``pre_response`` adds the response so far, the
            pending ``tool_calls`` and the ``response_window``, and ``post_complete``
            (or an Aperture that names no stage) sends the completed exchange.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | ApertureHookAccepted | AperturePreRequestResponse | AperturePreResponseResponse]
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
    body: ApertureDelivery,
) -> (
    Any
    | ApertureHookAccepted
    | AperturePreRequestResponse
    | AperturePreResponseResponse
    | None
):
    """Aperture Hook

     Serve every Tailscale Aperture hook stage from one URL, switching on metadata.stage.

    pre_request adds Watcher's fixed notice to the provider request, without
    grading. pre_response evaluates the pending tool calls before Aperture
    releases them and answers allow, per-call edits (a notice through the
    client's shell tool, or removal) or a block. post_complete, or a delivery
    that names no stage, is observed asynchronously like
    POST /v1/hooks/aperture/entire-request and answered 202. The API key must
    have sessions:write:any so metadata.login_name can attribute the session.

    Configure two Aperture hooks with this URL: one fail_open hook for the
    pre_request and entire_request events, and one tool_call_pre_response hook
    with fail_policy="fail_closed", block_response="message",
    fail_response="message" and a timeout above 300 seconds. Send
    request_body, response_body and tools.

    Args:
        body (ApertureDelivery): Any delivery to Watcher's single Aperture hook URL;
            ``metadata.stage`` says which stage sent it.

            The fields are the union of the three stages' payloads: ``pre_request``
            sends only the request, ``pre_response`` adds the response so far, the
            pending ``tool_calls`` and the ``response_window``, and ``post_complete``
            (or an Aperture that names no stage) sends the completed exchange.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | ApertureHookAccepted | AperturePreRequestResponse | AperturePreResponseResponse
    """

    return sync_detailed(
        client=client,
        body=body,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient | Client,
    body: ApertureDelivery,
) -> Response[
    Any
    | ApertureHookAccepted
    | AperturePreRequestResponse
    | AperturePreResponseResponse
]:
    """Aperture Hook

     Serve every Tailscale Aperture hook stage from one URL, switching on metadata.stage.

    pre_request adds Watcher's fixed notice to the provider request, without
    grading. pre_response evaluates the pending tool calls before Aperture
    releases them and answers allow, per-call edits (a notice through the
    client's shell tool, or removal) or a block. post_complete, or a delivery
    that names no stage, is observed asynchronously like
    POST /v1/hooks/aperture/entire-request and answered 202. The API key must
    have sessions:write:any so metadata.login_name can attribute the session.

    Configure two Aperture hooks with this URL: one fail_open hook for the
    pre_request and entire_request events, and one tool_call_pre_response hook
    with fail_policy="fail_closed", block_response="message",
    fail_response="message" and a timeout above 300 seconds. Send
    request_body, response_body and tools.

    Args:
        body (ApertureDelivery): Any delivery to Watcher's single Aperture hook URL;
            ``metadata.stage`` says which stage sent it.

            The fields are the union of the three stages' payloads: ``pre_request``
            sends only the request, ``pre_response`` adds the response so far, the
            pending ``tool_calls`` and the ``response_window``, and ``post_complete``
            (or an Aperture that names no stage) sends the completed exchange.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | ApertureHookAccepted | AperturePreRequestResponse | AperturePreResponseResponse]
    """

    kwargs = _get_kwargs(
        body=body,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient | Client,
    body: ApertureDelivery,
) -> (
    Any
    | ApertureHookAccepted
    | AperturePreRequestResponse
    | AperturePreResponseResponse
    | None
):
    """Aperture Hook

     Serve every Tailscale Aperture hook stage from one URL, switching on metadata.stage.

    pre_request adds Watcher's fixed notice to the provider request, without
    grading. pre_response evaluates the pending tool calls before Aperture
    releases them and answers allow, per-call edits (a notice through the
    client's shell tool, or removal) or a block. post_complete, or a delivery
    that names no stage, is observed asynchronously like
    POST /v1/hooks/aperture/entire-request and answered 202. The API key must
    have sessions:write:any so metadata.login_name can attribute the session.

    Configure two Aperture hooks with this URL: one fail_open hook for the
    pre_request and entire_request events, and one tool_call_pre_response hook
    with fail_policy="fail_closed", block_response="message",
    fail_response="message" and a timeout above 300 seconds. Send
    request_body, response_body and tools.

    Args:
        body (ApertureDelivery): Any delivery to Watcher's single Aperture hook URL;
            ``metadata.stage`` says which stage sent it.

            The fields are the union of the three stages' payloads: ``pre_request``
            sends only the request, ``pre_response`` adds the response so far, the
            pending ``tool_calls`` and the ``response_window``, and ``post_complete``
            (or an Aperture that names no stage) sends the completed exchange.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | ApertureHookAccepted | AperturePreRequestResponse | AperturePreResponseResponse
    """

    return (
        await asyncio_detailed(
            client=client,
            body=body,
        )
    ).parsed
