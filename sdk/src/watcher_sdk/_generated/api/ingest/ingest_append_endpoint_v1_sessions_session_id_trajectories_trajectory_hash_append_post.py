from http import HTTPStatus
from typing import Any
from urllib.parse import quote
from uuid import UUID

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.ingest_append_request import IngestAppendRequest
from ...models.ingest_response import IngestResponse
from ...types import Response


def _get_kwargs(
    session_id: UUID,
    trajectory_hash: str,
    *,
    body: IngestAppendRequest,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/v1/sessions/{session_id}/trajectories/{trajectory_hash}/append".format(
            session_id=quote(str(session_id), safe=""),
            trajectory_hash=quote(str(trajectory_hash), safe=""),
        ),
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> HTTPValidationError | IngestResponse | None:
    if response.status_code == 200:
        response_200 = IngestResponse.from_dict(response.json())

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
) -> Response[HTTPValidationError | IngestResponse]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    session_id: UUID,
    trajectory_hash: str,
    *,
    client: AuthenticatedClient | Client,
    body: IngestAppendRequest,
) -> Response[HTTPValidationError | IngestResponse]:
    """Ingest Append Endpoint

     Append a delta of transcript entries to an existing session's chain.

    ``trajectory_id`` names the anchor: the last message the client
    successfully uploaded. The delta continues the chain after it, producing
    rows identical to a full re-upload of the whole transcript. Clients fall
    back to POST /v1/ingest on any 404 or 409 from this route.

    Service keys carrying ``sessions:write:any`` may append across owners;
    those carrying only ``sessions:ingest`` may append only to unattributed
    sessions.

    Args:
        session_id (UUID):
        trajectory_hash (str):
        body (IngestAppendRequest): Request body for POST
            /v1/sessions/{session_id}/trajectories/{trajectory_id}/append.

            Appends a delta of raw transcript entries to an existing session's chain.
            The session and the anchor (the trajectory_id of the last message the
            client successfully uploaded) are named in the path; the server continues
            the chain after the anchor, so a session ingested through any mix of full
            and append uploads stores rows identical to full-only ingestion. Tailscale
            Aperture logs are whole-file proxy captures with no client-side cursor, so
            they have no append form.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | IngestResponse]
    """

    kwargs = _get_kwargs(
        session_id=session_id,
        trajectory_hash=trajectory_hash,
        body=body,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    session_id: UUID,
    trajectory_hash: str,
    *,
    client: AuthenticatedClient | Client,
    body: IngestAppendRequest,
) -> HTTPValidationError | IngestResponse | None:
    """Ingest Append Endpoint

     Append a delta of transcript entries to an existing session's chain.

    ``trajectory_id`` names the anchor: the last message the client
    successfully uploaded. The delta continues the chain after it, producing
    rows identical to a full re-upload of the whole transcript. Clients fall
    back to POST /v1/ingest on any 404 or 409 from this route.

    Service keys carrying ``sessions:write:any`` may append across owners;
    those carrying only ``sessions:ingest`` may append only to unattributed
    sessions.

    Args:
        session_id (UUID):
        trajectory_hash (str):
        body (IngestAppendRequest): Request body for POST
            /v1/sessions/{session_id}/trajectories/{trajectory_id}/append.

            Appends a delta of raw transcript entries to an existing session's chain.
            The session and the anchor (the trajectory_id of the last message the
            client successfully uploaded) are named in the path; the server continues
            the chain after the anchor, so a session ingested through any mix of full
            and append uploads stores rows identical to full-only ingestion. Tailscale
            Aperture logs are whole-file proxy captures with no client-side cursor, so
            they have no append form.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | IngestResponse
    """

    return sync_detailed(
        session_id=session_id,
        trajectory_hash=trajectory_hash,
        client=client,
        body=body,
    ).parsed


async def asyncio_detailed(
    session_id: UUID,
    trajectory_hash: str,
    *,
    client: AuthenticatedClient | Client,
    body: IngestAppendRequest,
) -> Response[HTTPValidationError | IngestResponse]:
    """Ingest Append Endpoint

     Append a delta of transcript entries to an existing session's chain.

    ``trajectory_id`` names the anchor: the last message the client
    successfully uploaded. The delta continues the chain after it, producing
    rows identical to a full re-upload of the whole transcript. Clients fall
    back to POST /v1/ingest on any 404 or 409 from this route.

    Service keys carrying ``sessions:write:any`` may append across owners;
    those carrying only ``sessions:ingest`` may append only to unattributed
    sessions.

    Args:
        session_id (UUID):
        trajectory_hash (str):
        body (IngestAppendRequest): Request body for POST
            /v1/sessions/{session_id}/trajectories/{trajectory_id}/append.

            Appends a delta of raw transcript entries to an existing session's chain.
            The session and the anchor (the trajectory_id of the last message the
            client successfully uploaded) are named in the path; the server continues
            the chain after the anchor, so a session ingested through any mix of full
            and append uploads stores rows identical to full-only ingestion. Tailscale
            Aperture logs are whole-file proxy captures with no client-side cursor, so
            they have no append form.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | IngestResponse]
    """

    kwargs = _get_kwargs(
        session_id=session_id,
        trajectory_hash=trajectory_hash,
        body=body,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    session_id: UUID,
    trajectory_hash: str,
    *,
    client: AuthenticatedClient | Client,
    body: IngestAppendRequest,
) -> HTTPValidationError | IngestResponse | None:
    """Ingest Append Endpoint

     Append a delta of transcript entries to an existing session's chain.

    ``trajectory_id`` names the anchor: the last message the client
    successfully uploaded. The delta continues the chain after it, producing
    rows identical to a full re-upload of the whole transcript. Clients fall
    back to POST /v1/ingest on any 404 or 409 from this route.

    Service keys carrying ``sessions:write:any`` may append across owners;
    those carrying only ``sessions:ingest`` may append only to unattributed
    sessions.

    Args:
        session_id (UUID):
        trajectory_hash (str):
        body (IngestAppendRequest): Request body for POST
            /v1/sessions/{session_id}/trajectories/{trajectory_id}/append.

            Appends a delta of raw transcript entries to an existing session's chain.
            The session and the anchor (the trajectory_id of the last message the
            client successfully uploaded) are named in the path; the server continues
            the chain after the anchor, so a session ingested through any mix of full
            and append uploads stores rows identical to full-only ingestion. Tailscale
            Aperture logs are whole-file proxy captures with no client-side cursor, so
            they have no append form.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | IngestResponse
    """

    return (
        await asyncio_detailed(
            session_id=session_id,
            trajectory_hash=trajectory_hash,
            client=client,
            body=body,
        )
    ).parsed
