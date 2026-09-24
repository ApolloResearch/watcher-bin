from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.trajectory_detail_response import TrajectoryDetailResponse
from ...models.trajectory_view import TrajectoryView
from ...types import UNSET, Response, Unset


def _get_kwargs(
    session_id: str,
    trajectory_id: str,
    *,
    view: TrajectoryView | Unset = UNSET,
) -> dict[str, Any]:

    params: dict[str, Any] = {}

    json_view: str | Unset = UNSET
    if not isinstance(view, Unset):
        json_view = view.value

    params["view"] = json_view

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/v1/sessions/{session_id}/trajectories/{trajectory_id}".format(
            session_id=quote(str(session_id), safe=""),
            trajectory_id=quote(str(trajectory_id), safe=""),
        ),
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> HTTPValidationError | TrajectoryDetailResponse | None:
    if response.status_code == 200:
        response_200 = TrajectoryDetailResponse.from_dict(response.json())

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
) -> Response[HTTPValidationError | TrajectoryDetailResponse]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    session_id: str,
    trajectory_id: str,
    *,
    client: AuthenticatedClient | Client,
    view: TrajectoryView | Unset = UNSET,
) -> Response[HTTPValidationError | TrajectoryDetailResponse]:
    """Get Session Trajectory Detail

     Get full trajectory detail within a session. 404 for sessions the caller can't read.

    The ``view`` parameter picks the payload shape and defaults to ``truncated``,
    which caps tool outputs and user pastes and stubs out ``data`` content blocks,
    leaving marker fields (``content_truncated``, ``content_original_chars``) so
    clients can offer a full fetch. Callers that need storage-faithful message
    content must explicitly request ``extended``.

    The literal trajectory id ``latest`` resolves server-side to the session's
    most recent trajectory (the response carries the resolved id), so
    session-scoped links can load a transcript in a single request. 404 when
    the session has no trajectories.

    Returns at most one grade: the most recent non-errored grade recorded
    anywhere on the requested trajectory's hash chain (a grade is stored
    against the trajectory hash current when it ran, so earlier grades sit on
    prefix hashes). A trajectory whose chain was never graded falls back to
    the session's most recent grade, so a graded session never presents as
    ungraded; errored grades are returned only when nothing else exists.

    Extended-thinking signatures (opaque replay payloads inside reasoning content
    blocks) are omitted from message content to keep responses small; the readable
    reasoning text is unaffected.

    Args:
        session_id (str):
        trajectory_id (str):
        view (TrajectoryView | Unset): Content density of a trajectory response.

            ``truncated`` elides heavy payloads for display: tool outputs and user pastes are
            capped with ``content_truncated``/``content_original_chars`` marker fields and
            ``data`` content blocks are replaced by size stubs. ``extended`` is
            storage-faithful. ``truncated`` is the default, so a data consumer (research
            export, offline analysis) must explicitly request ``extended`` — omitting the
            parameter never ships storage-faithful payloads by accident.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | TrajectoryDetailResponse]
    """

    kwargs = _get_kwargs(
        session_id=session_id,
        trajectory_id=trajectory_id,
        view=view,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    session_id: str,
    trajectory_id: str,
    *,
    client: AuthenticatedClient | Client,
    view: TrajectoryView | Unset = UNSET,
) -> HTTPValidationError | TrajectoryDetailResponse | None:
    """Get Session Trajectory Detail

     Get full trajectory detail within a session. 404 for sessions the caller can't read.

    The ``view`` parameter picks the payload shape and defaults to ``truncated``,
    which caps tool outputs and user pastes and stubs out ``data`` content blocks,
    leaving marker fields (``content_truncated``, ``content_original_chars``) so
    clients can offer a full fetch. Callers that need storage-faithful message
    content must explicitly request ``extended``.

    The literal trajectory id ``latest`` resolves server-side to the session's
    most recent trajectory (the response carries the resolved id), so
    session-scoped links can load a transcript in a single request. 404 when
    the session has no trajectories.

    Returns at most one grade: the most recent non-errored grade recorded
    anywhere on the requested trajectory's hash chain (a grade is stored
    against the trajectory hash current when it ran, so earlier grades sit on
    prefix hashes). A trajectory whose chain was never graded falls back to
    the session's most recent grade, so a graded session never presents as
    ungraded; errored grades are returned only when nothing else exists.

    Extended-thinking signatures (opaque replay payloads inside reasoning content
    blocks) are omitted from message content to keep responses small; the readable
    reasoning text is unaffected.

    Args:
        session_id (str):
        trajectory_id (str):
        view (TrajectoryView | Unset): Content density of a trajectory response.

            ``truncated`` elides heavy payloads for display: tool outputs and user pastes are
            capped with ``content_truncated``/``content_original_chars`` marker fields and
            ``data`` content blocks are replaced by size stubs. ``extended`` is
            storage-faithful. ``truncated`` is the default, so a data consumer (research
            export, offline analysis) must explicitly request ``extended`` — omitting the
            parameter never ships storage-faithful payloads by accident.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | TrajectoryDetailResponse
    """

    return sync_detailed(
        session_id=session_id,
        trajectory_id=trajectory_id,
        client=client,
        view=view,
    ).parsed


async def asyncio_detailed(
    session_id: str,
    trajectory_id: str,
    *,
    client: AuthenticatedClient | Client,
    view: TrajectoryView | Unset = UNSET,
) -> Response[HTTPValidationError | TrajectoryDetailResponse]:
    """Get Session Trajectory Detail

     Get full trajectory detail within a session. 404 for sessions the caller can't read.

    The ``view`` parameter picks the payload shape and defaults to ``truncated``,
    which caps tool outputs and user pastes and stubs out ``data`` content blocks,
    leaving marker fields (``content_truncated``, ``content_original_chars``) so
    clients can offer a full fetch. Callers that need storage-faithful message
    content must explicitly request ``extended``.

    The literal trajectory id ``latest`` resolves server-side to the session's
    most recent trajectory (the response carries the resolved id), so
    session-scoped links can load a transcript in a single request. 404 when
    the session has no trajectories.

    Returns at most one grade: the most recent non-errored grade recorded
    anywhere on the requested trajectory's hash chain (a grade is stored
    against the trajectory hash current when it ran, so earlier grades sit on
    prefix hashes). A trajectory whose chain was never graded falls back to
    the session's most recent grade, so a graded session never presents as
    ungraded; errored grades are returned only when nothing else exists.

    Extended-thinking signatures (opaque replay payloads inside reasoning content
    blocks) are omitted from message content to keep responses small; the readable
    reasoning text is unaffected.

    Args:
        session_id (str):
        trajectory_id (str):
        view (TrajectoryView | Unset): Content density of a trajectory response.

            ``truncated`` elides heavy payloads for display: tool outputs and user pastes are
            capped with ``content_truncated``/``content_original_chars`` marker fields and
            ``data`` content blocks are replaced by size stubs. ``extended`` is
            storage-faithful. ``truncated`` is the default, so a data consumer (research
            export, offline analysis) must explicitly request ``extended`` — omitting the
            parameter never ships storage-faithful payloads by accident.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | TrajectoryDetailResponse]
    """

    kwargs = _get_kwargs(
        session_id=session_id,
        trajectory_id=trajectory_id,
        view=view,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    session_id: str,
    trajectory_id: str,
    *,
    client: AuthenticatedClient | Client,
    view: TrajectoryView | Unset = UNSET,
) -> HTTPValidationError | TrajectoryDetailResponse | None:
    """Get Session Trajectory Detail

     Get full trajectory detail within a session. 404 for sessions the caller can't read.

    The ``view`` parameter picks the payload shape and defaults to ``truncated``,
    which caps tool outputs and user pastes and stubs out ``data`` content blocks,
    leaving marker fields (``content_truncated``, ``content_original_chars``) so
    clients can offer a full fetch. Callers that need storage-faithful message
    content must explicitly request ``extended``.

    The literal trajectory id ``latest`` resolves server-side to the session's
    most recent trajectory (the response carries the resolved id), so
    session-scoped links can load a transcript in a single request. 404 when
    the session has no trajectories.

    Returns at most one grade: the most recent non-errored grade recorded
    anywhere on the requested trajectory's hash chain (a grade is stored
    against the trajectory hash current when it ran, so earlier grades sit on
    prefix hashes). A trajectory whose chain was never graded falls back to
    the session's most recent grade, so a graded session never presents as
    ungraded; errored grades are returned only when nothing else exists.

    Extended-thinking signatures (opaque replay payloads inside reasoning content
    blocks) are omitted from message content to keep responses small; the readable
    reasoning text is unaffected.

    Args:
        session_id (str):
        trajectory_id (str):
        view (TrajectoryView | Unset): Content density of a trajectory response.

            ``truncated`` elides heavy payloads for display: tool outputs and user pastes are
            capped with ``content_truncated``/``content_original_chars`` marker fields and
            ``data`` content blocks are replaced by size stubs. ``extended`` is
            storage-faithful. ``truncated`` is the default, so a data consumer (research
            export, offline analysis) must explicitly request ``extended`` — omitting the
            parameter never ships storage-faithful payloads by accident.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | TrajectoryDetailResponse
    """

    return (
        await asyncio_detailed(
            session_id=session_id,
            trajectory_id=trajectory_id,
            client=client,
            view=view,
        )
    ).parsed
