from http import HTTPStatus
from typing import Any, cast

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.ingest_request import IngestRequest
from ...models.ingest_response import IngestResponse
from ...types import Response


def _get_kwargs(
    *,
    body: IngestRequest,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/v1/ingest",
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Any | HTTPValidationError | IngestResponse | None:
    if response.status_code == 200:
        response_200 = IngestResponse.from_dict(response.json())

        return response_200

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
) -> Response[Any | HTTPValidationError | IngestResponse]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient | Client,
    body: IngestRequest,
) -> Response[Any | HTTPValidationError | IngestResponse]:
    """Ingest

     Ingest one or more trajectories. Returns leaf hashes and session ID.

    User attribution: signed-in users write their own sessions. Service keys
    carrying ``sessions:write:any`` may honor ``identity.login_name`` for
    proxy-capture (Tailscale Aperture) attribution; keys carrying only
    ``sessions:ingest`` write unattributed sessions.

    A Claude Code session id or Codex thread id names one session per
    organization. An upload attributed to a user (a signed-in user's, or one
    attributed through ``identity.login_name``) joins that session when it has
    no owner and makes the user its owner, including its linked descendants.
    A conflicting known owner in its ancestry or descendants also rejects the
    attribution atomically. When another user owns it, the
    request is rejected with 409 ``session_owner_conflict``: that trajectory
    is not stored, earlier trajectories in the request stay stored, and later
    ones are not processed. An upload attributed to no user joins the session
    whoever owns it and leaves the owner unchanged.

    Args:
        body (IngestRequest): Request body for POST /v1/ingest.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError | IngestResponse]
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
    body: IngestRequest,
) -> Any | HTTPValidationError | IngestResponse | None:
    """Ingest

     Ingest one or more trajectories. Returns leaf hashes and session ID.

    User attribution: signed-in users write their own sessions. Service keys
    carrying ``sessions:write:any`` may honor ``identity.login_name`` for
    proxy-capture (Tailscale Aperture) attribution; keys carrying only
    ``sessions:ingest`` write unattributed sessions.

    A Claude Code session id or Codex thread id names one session per
    organization. An upload attributed to a user (a signed-in user's, or one
    attributed through ``identity.login_name``) joins that session when it has
    no owner and makes the user its owner, including its linked descendants.
    A conflicting known owner in its ancestry or descendants also rejects the
    attribution atomically. When another user owns it, the
    request is rejected with 409 ``session_owner_conflict``: that trajectory
    is not stored, earlier trajectories in the request stay stored, and later
    ones are not processed. An upload attributed to no user joins the session
    whoever owns it and leaves the owner unchanged.

    Args:
        body (IngestRequest): Request body for POST /v1/ingest.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError | IngestResponse
    """

    return sync_detailed(
        client=client,
        body=body,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient | Client,
    body: IngestRequest,
) -> Response[Any | HTTPValidationError | IngestResponse]:
    """Ingest

     Ingest one or more trajectories. Returns leaf hashes and session ID.

    User attribution: signed-in users write their own sessions. Service keys
    carrying ``sessions:write:any`` may honor ``identity.login_name`` for
    proxy-capture (Tailscale Aperture) attribution; keys carrying only
    ``sessions:ingest`` write unattributed sessions.

    A Claude Code session id or Codex thread id names one session per
    organization. An upload attributed to a user (a signed-in user's, or one
    attributed through ``identity.login_name``) joins that session when it has
    no owner and makes the user its owner, including its linked descendants.
    A conflicting known owner in its ancestry or descendants also rejects the
    attribution atomically. When another user owns it, the
    request is rejected with 409 ``session_owner_conflict``: that trajectory
    is not stored, earlier trajectories in the request stay stored, and later
    ones are not processed. An upload attributed to no user joins the session
    whoever owns it and leaves the owner unchanged.

    Args:
        body (IngestRequest): Request body for POST /v1/ingest.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError | IngestResponse]
    """

    kwargs = _get_kwargs(
        body=body,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient | Client,
    body: IngestRequest,
) -> Any | HTTPValidationError | IngestResponse | None:
    """Ingest

     Ingest one or more trajectories. Returns leaf hashes and session ID.

    User attribution: signed-in users write their own sessions. Service keys
    carrying ``sessions:write:any`` may honor ``identity.login_name`` for
    proxy-capture (Tailscale Aperture) attribution; keys carrying only
    ``sessions:ingest`` write unattributed sessions.

    A Claude Code session id or Codex thread id names one session per
    organization. An upload attributed to a user (a signed-in user's, or one
    attributed through ``identity.login_name``) joins that session when it has
    no owner and makes the user its owner, including its linked descendants.
    A conflicting known owner in its ancestry or descendants also rejects the
    attribution atomically. When another user owns it, the
    request is rejected with 409 ``session_owner_conflict``: that trajectory
    is not stored, earlier trajectories in the request stay stored, and later
    ones are not processed. An upload attributed to no user joins the session
    whoever owns it and leaves the owner unchanged.

    Args:
        body (IngestRequest): Request body for POST /v1/ingest.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError | IngestResponse
    """

    return (
        await asyncio_detailed(
            client=client,
            body=body,
        )
    ).parsed
