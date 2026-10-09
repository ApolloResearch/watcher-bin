from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.grade_by_monitor_v1_monitors_role_grade_post_role import (
    GradeByMonitorV1MonitorsRoleGradePostRole,
)
from ...models.grade_response import GradeResponse
from ...models.http_validation_error import HTTPValidationError
from ...models.monitoring_request import MonitoringRequest
from ...types import Response


def _get_kwargs(
    role: GradeByMonitorV1MonitorsRoleGradePostRole,
    *,
    body: MonitoringRequest,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/v1/monitors/{role}/grade".format(
            role=quote(str(role), safe=""),
        ),
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Any | GradeResponse | HTTPValidationError | None:
    if response.status_code == 200:
        response_200 = GradeResponse.from_dict(response.json())

        return response_200

    if response.status_code == 422:
        response_422 = HTTPValidationError.from_dict(response.json())

        return response_422

    if response.status_code == 499:
        response_499 = cast(Any, None)
        return response_499

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Response[Any | GradeResponse | HTTPValidationError]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    role: GradeByMonitorV1MonitorsRoleGradePostRole,
    *,
    client: AuthenticatedClient | Client,
    body: MonitoringRequest,
) -> Response[Any | GradeResponse | HTTPValidationError]:
    """Grade By Monitor

     Grade with the monitor serving ``role`` — no grader UUID, model, or prompt client-side.

    Ephemeral ``messages`` grades persist as tool-call audit rows under the
    role's run kind (``policy_triage``/``policy_gateway``) and return a
    ``tool_call_grade_id`` per result, exactly like a UUID-addressed tool-call
    grade. DB-backed grading (``trajectory_ids`` + ``session_id``) requires
    ownership or ``sessions:grade:any``; content access is not required to run
    a server-managed monitor. Results respect findings and content permissions. Supplied-message
    grades require session write authority when attached to a session.
    Both modes enforce grading caps and usage allowances.

    Responses omit ``model``: which model a monitor runs is a server-side
    policy choice, not part of the client contract.

    Args:
        role (GradeByMonitorV1MonitorsRoleGradePostRole):
        body (MonitoringRequest): Request body for POST /v1/monitors/{role}/grade.

            Names *what* to monitor; the server owns *how*. The monitor in the path
            resolves server-side to its prompt, model, reasoning, and context policy,
            and the tool-call audit kind derives from the role.

            Three mutually exclusive payload modes:

            - ``input`` — structured monitoring of one gated tool call: the transcript
              and the call as data, formatted into the monitor prompt server-side.
              The mode clients are expected to use.
            - ``messages`` — pre-assembled message lists, graded as sent.
            - ``trajectory_ids`` + ``session_id`` — DB-backed grading of stored
              trajectories.

            On the two ephemeral modes the caller may also send ``session_id`` +
            ``tool_use_id`` to identify the gated call being graded (the role's run
            kind makes every ephemeral grade here a tool-call audit row).

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | GradeResponse | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        role=role,
        body=body,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    role: GradeByMonitorV1MonitorsRoleGradePostRole,
    *,
    client: AuthenticatedClient | Client,
    body: MonitoringRequest,
) -> Any | GradeResponse | HTTPValidationError | None:
    """Grade By Monitor

     Grade with the monitor serving ``role`` — no grader UUID, model, or prompt client-side.

    Ephemeral ``messages`` grades persist as tool-call audit rows under the
    role's run kind (``policy_triage``/``policy_gateway``) and return a
    ``tool_call_grade_id`` per result, exactly like a UUID-addressed tool-call
    grade. DB-backed grading (``trajectory_ids`` + ``session_id``) requires
    ownership or ``sessions:grade:any``; content access is not required to run
    a server-managed monitor. Results respect findings and content permissions. Supplied-message
    grades require session write authority when attached to a session.
    Both modes enforce grading caps and usage allowances.

    Responses omit ``model``: which model a monitor runs is a server-side
    policy choice, not part of the client contract.

    Args:
        role (GradeByMonitorV1MonitorsRoleGradePostRole):
        body (MonitoringRequest): Request body for POST /v1/monitors/{role}/grade.

            Names *what* to monitor; the server owns *how*. The monitor in the path
            resolves server-side to its prompt, model, reasoning, and context policy,
            and the tool-call audit kind derives from the role.

            Three mutually exclusive payload modes:

            - ``input`` — structured monitoring of one gated tool call: the transcript
              and the call as data, formatted into the monitor prompt server-side.
              The mode clients are expected to use.
            - ``messages`` — pre-assembled message lists, graded as sent.
            - ``trajectory_ids`` + ``session_id`` — DB-backed grading of stored
              trajectories.

            On the two ephemeral modes the caller may also send ``session_id`` +
            ``tool_use_id`` to identify the gated call being graded (the role's run
            kind makes every ephemeral grade here a tool-call audit row).

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | GradeResponse | HTTPValidationError
    """

    return sync_detailed(
        role=role,
        client=client,
        body=body,
    ).parsed


async def asyncio_detailed(
    role: GradeByMonitorV1MonitorsRoleGradePostRole,
    *,
    client: AuthenticatedClient | Client,
    body: MonitoringRequest,
) -> Response[Any | GradeResponse | HTTPValidationError]:
    """Grade By Monitor

     Grade with the monitor serving ``role`` — no grader UUID, model, or prompt client-side.

    Ephemeral ``messages`` grades persist as tool-call audit rows under the
    role's run kind (``policy_triage``/``policy_gateway``) and return a
    ``tool_call_grade_id`` per result, exactly like a UUID-addressed tool-call
    grade. DB-backed grading (``trajectory_ids`` + ``session_id``) requires
    ownership or ``sessions:grade:any``; content access is not required to run
    a server-managed monitor. Results respect findings and content permissions. Supplied-message
    grades require session write authority when attached to a session.
    Both modes enforce grading caps and usage allowances.

    Responses omit ``model``: which model a monitor runs is a server-side
    policy choice, not part of the client contract.

    Args:
        role (GradeByMonitorV1MonitorsRoleGradePostRole):
        body (MonitoringRequest): Request body for POST /v1/monitors/{role}/grade.

            Names *what* to monitor; the server owns *how*. The monitor in the path
            resolves server-side to its prompt, model, reasoning, and context policy,
            and the tool-call audit kind derives from the role.

            Three mutually exclusive payload modes:

            - ``input`` — structured monitoring of one gated tool call: the transcript
              and the call as data, formatted into the monitor prompt server-side.
              The mode clients are expected to use.
            - ``messages`` — pre-assembled message lists, graded as sent.
            - ``trajectory_ids`` + ``session_id`` — DB-backed grading of stored
              trajectories.

            On the two ephemeral modes the caller may also send ``session_id`` +
            ``tool_use_id`` to identify the gated call being graded (the role's run
            kind makes every ephemeral grade here a tool-call audit row).

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | GradeResponse | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        role=role,
        body=body,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    role: GradeByMonitorV1MonitorsRoleGradePostRole,
    *,
    client: AuthenticatedClient | Client,
    body: MonitoringRequest,
) -> Any | GradeResponse | HTTPValidationError | None:
    """Grade By Monitor

     Grade with the monitor serving ``role`` — no grader UUID, model, or prompt client-side.

    Ephemeral ``messages`` grades persist as tool-call audit rows under the
    role's run kind (``policy_triage``/``policy_gateway``) and return a
    ``tool_call_grade_id`` per result, exactly like a UUID-addressed tool-call
    grade. DB-backed grading (``trajectory_ids`` + ``session_id``) requires
    ownership or ``sessions:grade:any``; content access is not required to run
    a server-managed monitor. Results respect findings and content permissions. Supplied-message
    grades require session write authority when attached to a session.
    Both modes enforce grading caps and usage allowances.

    Responses omit ``model``: which model a monitor runs is a server-side
    policy choice, not part of the client contract.

    Args:
        role (GradeByMonitorV1MonitorsRoleGradePostRole):
        body (MonitoringRequest): Request body for POST /v1/monitors/{role}/grade.

            Names *what* to monitor; the server owns *how*. The monitor in the path
            resolves server-side to its prompt, model, reasoning, and context policy,
            and the tool-call audit kind derives from the role.

            Three mutually exclusive payload modes:

            - ``input`` — structured monitoring of one gated tool call: the transcript
              and the call as data, formatted into the monitor prompt server-side.
              The mode clients are expected to use.
            - ``messages`` — pre-assembled message lists, graded as sent.
            - ``trajectory_ids`` + ``session_id`` — DB-backed grading of stored
              trajectories.

            On the two ephemeral modes the caller may also send ``session_id`` +
            ``tool_use_id`` to identify the gated call being graded (the role's run
            kind makes every ephemeral grade here a tool-call audit row).

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | GradeResponse | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            role=role,
            client=client,
            body=body,
        )
    ).parsed
