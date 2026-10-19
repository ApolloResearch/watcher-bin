from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.tool_call_detail_response import ToolCallDetailResponse
from ...types import UNSET, Response


def _get_kwargs(
    session_id: str,
    *,
    tool_use_id: str,
) -> dict[str, Any]:

    params: dict[str, Any] = {}

    params["tool_use_id"] = tool_use_id

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/v1/sessions/{session_id}/tool-call".format(
            session_id=quote(str(session_id), safe=""),
        ),
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> HTTPValidationError | ToolCallDetailResponse | None:
    if response.status_code == 200:
        response_200 = ToolCallDetailResponse.from_dict(response.json())

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
) -> Response[HTTPValidationError | ToolCallDetailResponse]:
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
    tool_use_id: str,
) -> Response[HTTPValidationError | ToolCallDetailResponse]:
    """Get Session Tool Call

     Read one exact tool call without its surrounding transcript.

    Findings and content are independently authorized with session grants,
    ownership and content approvals. The flagged-call content permission also
    permits arguments/results for calls with a recorded risk-driven block or
    escalation, without permitting surrounding messages. Restricted fields are null; access flags
    distinguish restriction from an absent result or decision. Grader input
    transcripts are never returned. Tool-use IDs are query parameters because
    they can contain slashes and '#'. Returns 404 for missing, inaccessible or
    scrubbed sessions and missing calls, and 400 for malformed session UUIDs.

    Args:
        session_id (str):
        tool_use_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | ToolCallDetailResponse]
    """

    kwargs = _get_kwargs(
        session_id=session_id,
        tool_use_id=tool_use_id,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    session_id: str,
    *,
    client: AuthenticatedClient | Client,
    tool_use_id: str,
) -> HTTPValidationError | ToolCallDetailResponse | None:
    """Get Session Tool Call

     Read one exact tool call without its surrounding transcript.

    Findings and content are independently authorized with session grants,
    ownership and content approvals. The flagged-call content permission also
    permits arguments/results for calls with a recorded risk-driven block or
    escalation, without permitting surrounding messages. Restricted fields are null; access flags
    distinguish restriction from an absent result or decision. Grader input
    transcripts are never returned. Tool-use IDs are query parameters because
    they can contain slashes and '#'. Returns 404 for missing, inaccessible or
    scrubbed sessions and missing calls, and 400 for malformed session UUIDs.

    Args:
        session_id (str):
        tool_use_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | ToolCallDetailResponse
    """

    return sync_detailed(
        session_id=session_id,
        client=client,
        tool_use_id=tool_use_id,
    ).parsed


async def asyncio_detailed(
    session_id: str,
    *,
    client: AuthenticatedClient | Client,
    tool_use_id: str,
) -> Response[HTTPValidationError | ToolCallDetailResponse]:
    """Get Session Tool Call

     Read one exact tool call without its surrounding transcript.

    Findings and content are independently authorized with session grants,
    ownership and content approvals. The flagged-call content permission also
    permits arguments/results for calls with a recorded risk-driven block or
    escalation, without permitting surrounding messages. Restricted fields are null; access flags
    distinguish restriction from an absent result or decision. Grader input
    transcripts are never returned. Tool-use IDs are query parameters because
    they can contain slashes and '#'. Returns 404 for missing, inaccessible or
    scrubbed sessions and missing calls, and 400 for malformed session UUIDs.

    Args:
        session_id (str):
        tool_use_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | ToolCallDetailResponse]
    """

    kwargs = _get_kwargs(
        session_id=session_id,
        tool_use_id=tool_use_id,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    session_id: str,
    *,
    client: AuthenticatedClient | Client,
    tool_use_id: str,
) -> HTTPValidationError | ToolCallDetailResponse | None:
    """Get Session Tool Call

     Read one exact tool call without its surrounding transcript.

    Findings and content are independently authorized with session grants,
    ownership and content approvals. The flagged-call content permission also
    permits arguments/results for calls with a recorded risk-driven block or
    escalation, without permitting surrounding messages. Restricted fields are null; access flags
    distinguish restriction from an absent result or decision. Grader input
    transcripts are never returned. Tool-use IDs are query parameters because
    they can contain slashes and '#'. Returns 404 for missing, inaccessible or
    scrubbed sessions and missing calls, and 400 for malformed session UUIDs.

    Args:
        session_id (str):
        tool_use_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | ToolCallDetailResponse
    """

    return (
        await asyncio_detailed(
            session_id=session_id,
            client=client,
            tool_use_id=tool_use_id,
        )
    ).parsed
