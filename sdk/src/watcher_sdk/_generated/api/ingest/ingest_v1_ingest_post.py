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

    if response.status_code == 503:
        response_503 = cast(Any, None)
        return response_503

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

    ``results[i]`` describes ``trajectories[i]``, including empty and duplicate
    inputs. Each result has a chunk endpoint, live leaf, and storage status.
    Set ``append_after`` and ``fork`` on the trajectory to continue or branch;
    either option requires exactly one Claude Code, Codex, or Copilot input. Released
    aggregate fields retain their batch semantics.

    User attribution: signed-in users write their own sessions. Service keys
    carrying ``sessions:write:any`` may honor ``identity.login_name`` for
    proxy-capture (Tailscale Aperture) attribution; keys carrying only
    ``sessions:ingest`` write unattributed sessions.

    Conversation IDs, aliases and transcript matching are scoped to the
    organisation, owner and compatible agent platform. Personal and ingest-only
    uploads using the same native ID record separate sessions. Attributed
    gateways and clients can share a session when their owner and IDs agree.
    Existing owners, including null owners, never change through uploads.
    Explicit cross-user write authority remains supported.

    A temporary recording conflict returns 503 with ``Retry-After``. Retry the
    request with bounded backoff. Earlier inputs in the batch stay stored and
    later ones are not processed.

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

    ``results[i]`` describes ``trajectories[i]``, including empty and duplicate
    inputs. Each result has a chunk endpoint, live leaf, and storage status.
    Set ``append_after`` and ``fork`` on the trajectory to continue or branch;
    either option requires exactly one Claude Code, Codex, or Copilot input. Released
    aggregate fields retain their batch semantics.

    User attribution: signed-in users write their own sessions. Service keys
    carrying ``sessions:write:any`` may honor ``identity.login_name`` for
    proxy-capture (Tailscale Aperture) attribution; keys carrying only
    ``sessions:ingest`` write unattributed sessions.

    Conversation IDs, aliases and transcript matching are scoped to the
    organisation, owner and compatible agent platform. Personal and ingest-only
    uploads using the same native ID record separate sessions. Attributed
    gateways and clients can share a session when their owner and IDs agree.
    Existing owners, including null owners, never change through uploads.
    Explicit cross-user write authority remains supported.

    A temporary recording conflict returns 503 with ``Retry-After``. Retry the
    request with bounded backoff. Earlier inputs in the batch stay stored and
    later ones are not processed.

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

    ``results[i]`` describes ``trajectories[i]``, including empty and duplicate
    inputs. Each result has a chunk endpoint, live leaf, and storage status.
    Set ``append_after`` and ``fork`` on the trajectory to continue or branch;
    either option requires exactly one Claude Code, Codex, or Copilot input. Released
    aggregate fields retain their batch semantics.

    User attribution: signed-in users write their own sessions. Service keys
    carrying ``sessions:write:any`` may honor ``identity.login_name`` for
    proxy-capture (Tailscale Aperture) attribution; keys carrying only
    ``sessions:ingest`` write unattributed sessions.

    Conversation IDs, aliases and transcript matching are scoped to the
    organisation, owner and compatible agent platform. Personal and ingest-only
    uploads using the same native ID record separate sessions. Attributed
    gateways and clients can share a session when their owner and IDs agree.
    Existing owners, including null owners, never change through uploads.
    Explicit cross-user write authority remains supported.

    A temporary recording conflict returns 503 with ``Retry-After``. Retry the
    request with bounded backoff. Earlier inputs in the batch stay stored and
    later ones are not processed.

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

    ``results[i]`` describes ``trajectories[i]``, including empty and duplicate
    inputs. Each result has a chunk endpoint, live leaf, and storage status.
    Set ``append_after`` and ``fork`` on the trajectory to continue or branch;
    either option requires exactly one Claude Code, Codex, or Copilot input. Released
    aggregate fields retain their batch semantics.

    User attribution: signed-in users write their own sessions. Service keys
    carrying ``sessions:write:any`` may honor ``identity.login_name`` for
    proxy-capture (Tailscale Aperture) attribution; keys carrying only
    ``sessions:ingest`` write unattributed sessions.

    Conversation IDs, aliases and transcript matching are scoped to the
    organisation, owner and compatible agent platform. Personal and ingest-only
    uploads using the same native ID record separate sessions. Attributed
    gateways and clients can share a session when their owner and IDs agree.
    Existing owners, including null owners, never change through uploads.
    Explicit cross-user write authority remains supported.

    A temporary recording conflict returns 503 with ``Retry-After``. Retry the
    request with bounded backoff. Earlier inputs in the batch stay stored and
    later ones are not processed.

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
