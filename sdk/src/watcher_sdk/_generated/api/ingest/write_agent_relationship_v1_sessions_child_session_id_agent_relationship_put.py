from http import HTTPStatus
from typing import Any
from urllib.parse import quote
from uuid import UUID

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.agent_relationship_request import AgentRelationshipRequest
from ...models.agent_relationship_response import AgentRelationshipResponse
from ...models.http_validation_error import HTTPValidationError
from ...types import Response


def _get_kwargs(
    child_session_id: UUID,
    *,
    body: AgentRelationshipRequest,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

    _kwargs: dict[str, Any] = {
        "method": "put",
        "url": "/v1/sessions/{child_session_id}/agent-relationship".format(
            child_session_id=quote(str(child_session_id), safe=""),
        ),
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> AgentRelationshipResponse | HTTPValidationError | None:
    if response.status_code == 200:
        response_200 = AgentRelationshipResponse.from_dict(response.json())

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
) -> Response[AgentRelationshipResponse | HTTPValidationError]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    child_session_id: UUID,
    *,
    client: AuthenticatedClient | Client,
    body: AgentRelationshipRequest,
) -> Response[AgentRelationshipResponse | HTTPValidationError]:
    """Write Agent Relationship

     Create a child's original parent link or fill missing spawning-call details.

    Both sessions must already exist and be writable under ingestion rules.
    Ingest-only keys may link unowned sessions or native Claude/Codex conversations,
    including after those conversations acquire an owner. Owning the parent does
    not authorize claiming an unowned child; users limited to their own sessions
    must first attribute the child through ingestion. New links apply known parent ownership to the
    child
    and its descendants; conflicting known owners return 409 owner_conflict with
    no partial attribution. Retries and spawning-call enrichment do not propagate
    ownership again. Other owned sessions require cross-user write permission.
    Missing or unauthorized sessions and missing explicit message hashes return
    404. Without a message hash, the server searches this parent
    for the native spawning-call ID; an absent call leaves the hash null in the
    successful response. Retry after ordinary ingestion to complete the link.
    Duplicate representations select the first inserted match. Invalid ancestry or
    conflicting established details return 409. Null details leave stored values
    unchanged; exact retries succeed even after transcript content is scrubbed.

    Args:
        child_session_id (UUID):
        body (AgentRelationshipRequest): Create a child's parent link or fill previously unknown
            spawning details.

            Omitted or null details leave existing values unchanged. Parent and resolved
            spawning details are immutable. A message hash requires its tool-use ID.
            Without a hash, the server looks up the native call in the parent's stored
            messages, selecting the first inserted match if representations repeat.
            Missing calls leave the hash unresolved; retry after ordinary ingestion.
            Both sessions must already exist.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[AgentRelationshipResponse | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        child_session_id=child_session_id,
        body=body,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    child_session_id: UUID,
    *,
    client: AuthenticatedClient | Client,
    body: AgentRelationshipRequest,
) -> AgentRelationshipResponse | HTTPValidationError | None:
    """Write Agent Relationship

     Create a child's original parent link or fill missing spawning-call details.

    Both sessions must already exist and be writable under ingestion rules.
    Ingest-only keys may link unowned sessions or native Claude/Codex conversations,
    including after those conversations acquire an owner. Owning the parent does
    not authorize claiming an unowned child; users limited to their own sessions
    must first attribute the child through ingestion. New links apply known parent ownership to the
    child
    and its descendants; conflicting known owners return 409 owner_conflict with
    no partial attribution. Retries and spawning-call enrichment do not propagate
    ownership again. Other owned sessions require cross-user write permission.
    Missing or unauthorized sessions and missing explicit message hashes return
    404. Without a message hash, the server searches this parent
    for the native spawning-call ID; an absent call leaves the hash null in the
    successful response. Retry after ordinary ingestion to complete the link.
    Duplicate representations select the first inserted match. Invalid ancestry or
    conflicting established details return 409. Null details leave stored values
    unchanged; exact retries succeed even after transcript content is scrubbed.

    Args:
        child_session_id (UUID):
        body (AgentRelationshipRequest): Create a child's parent link or fill previously unknown
            spawning details.

            Omitted or null details leave existing values unchanged. Parent and resolved
            spawning details are immutable. A message hash requires its tool-use ID.
            Without a hash, the server looks up the native call in the parent's stored
            messages, selecting the first inserted match if representations repeat.
            Missing calls leave the hash unresolved; retry after ordinary ingestion.
            Both sessions must already exist.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        AgentRelationshipResponse | HTTPValidationError
    """

    return sync_detailed(
        child_session_id=child_session_id,
        client=client,
        body=body,
    ).parsed


async def asyncio_detailed(
    child_session_id: UUID,
    *,
    client: AuthenticatedClient | Client,
    body: AgentRelationshipRequest,
) -> Response[AgentRelationshipResponse | HTTPValidationError]:
    """Write Agent Relationship

     Create a child's original parent link or fill missing spawning-call details.

    Both sessions must already exist and be writable under ingestion rules.
    Ingest-only keys may link unowned sessions or native Claude/Codex conversations,
    including after those conversations acquire an owner. Owning the parent does
    not authorize claiming an unowned child; users limited to their own sessions
    must first attribute the child through ingestion. New links apply known parent ownership to the
    child
    and its descendants; conflicting known owners return 409 owner_conflict with
    no partial attribution. Retries and spawning-call enrichment do not propagate
    ownership again. Other owned sessions require cross-user write permission.
    Missing or unauthorized sessions and missing explicit message hashes return
    404. Without a message hash, the server searches this parent
    for the native spawning-call ID; an absent call leaves the hash null in the
    successful response. Retry after ordinary ingestion to complete the link.
    Duplicate representations select the first inserted match. Invalid ancestry or
    conflicting established details return 409. Null details leave stored values
    unchanged; exact retries succeed even after transcript content is scrubbed.

    Args:
        child_session_id (UUID):
        body (AgentRelationshipRequest): Create a child's parent link or fill previously unknown
            spawning details.

            Omitted or null details leave existing values unchanged. Parent and resolved
            spawning details are immutable. A message hash requires its tool-use ID.
            Without a hash, the server looks up the native call in the parent's stored
            messages, selecting the first inserted match if representations repeat.
            Missing calls leave the hash unresolved; retry after ordinary ingestion.
            Both sessions must already exist.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[AgentRelationshipResponse | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        child_session_id=child_session_id,
        body=body,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    child_session_id: UUID,
    *,
    client: AuthenticatedClient | Client,
    body: AgentRelationshipRequest,
) -> AgentRelationshipResponse | HTTPValidationError | None:
    """Write Agent Relationship

     Create a child's original parent link or fill missing spawning-call details.

    Both sessions must already exist and be writable under ingestion rules.
    Ingest-only keys may link unowned sessions or native Claude/Codex conversations,
    including after those conversations acquire an owner. Owning the parent does
    not authorize claiming an unowned child; users limited to their own sessions
    must first attribute the child through ingestion. New links apply known parent ownership to the
    child
    and its descendants; conflicting known owners return 409 owner_conflict with
    no partial attribution. Retries and spawning-call enrichment do not propagate
    ownership again. Other owned sessions require cross-user write permission.
    Missing or unauthorized sessions and missing explicit message hashes return
    404. Without a message hash, the server searches this parent
    for the native spawning-call ID; an absent call leaves the hash null in the
    successful response. Retry after ordinary ingestion to complete the link.
    Duplicate representations select the first inserted match. Invalid ancestry or
    conflicting established details return 409. Null details leave stored values
    unchanged; exact retries succeed even after transcript content is scrubbed.

    Args:
        child_session_id (UUID):
        body (AgentRelationshipRequest): Create a child's parent link or fill previously unknown
            spawning details.

            Omitted or null details leave existing values unchanged. Parent and resolved
            spawning details are immutable. A message hash requires its tool-use ID.
            Without a hash, the server looks up the native call in the parent's stored
            messages, selecting the first inserted match if representations repeat.
            Missing calls leave the hash unresolved; retry after ordinary ingestion.
            Both sessions must already exist.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        AgentRelationshipResponse | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            child_session_id=child_session_id,
            client=client,
            body=body,
        )
    ).parsed
