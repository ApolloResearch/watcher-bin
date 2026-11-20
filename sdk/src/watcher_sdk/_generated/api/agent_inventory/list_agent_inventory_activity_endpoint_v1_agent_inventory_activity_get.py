from http import HTTPStatus
from typing import Any
from uuid import UUID

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.agent_inventory_activity_response import AgentInventoryActivityResponse
from ...models.http_validation_error import HTTPValidationError
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    installation_id: None | Unset | UUID = UNSET,
) -> dict[str, Any]:

    params: dict[str, Any] = {}

    json_installation_id: None | str | Unset
    if isinstance(installation_id, Unset):
        json_installation_id = UNSET
    elif isinstance(installation_id, UUID):
        json_installation_id = str(installation_id)
    else:
        json_installation_id = installation_id
    params["installation_id"] = json_installation_id

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/v1/agent-inventory/activity",
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> AgentInventoryActivityResponse | HTTPValidationError | None:
    if response.status_code == 200:
        response_200 = AgentInventoryActivityResponse.from_dict(response.json())

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
) -> Response[AgentInventoryActivityResponse | HTTPValidationError]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient | Client,
    installation_id: None | Unset | UUID = UNSET,
) -> Response[AgentInventoryActivityResponse | HTTPValidationError]:
    """List Agent Inventory Activity Endpoint

     List what changed on machines running the Watcher client in the last 7 days, newest first.

    Changes are found by comparing the reports each machine's client sent one after another: check-ins
    stopping,
    client updates, agents turned off or on, Watcher's hooks going missing or coming back, snoozes,
    enforcement
    mode changes and upload backlogs. For one machine (`installation_id`), every change in the 7 days.
    For the whole
    organization, the changes in the last 24 hours (`recent_since`) except check-ins stopping (the
    machine list's
    check-in state shows those), plus earlier changes that still hold when the machine's reports say
    when they
    began: an agent turned off, a turned-on agent's hooks missing, an active snooze, uploads backing up
    and grading
    paused. While the organization's own mode is paused (known only when Watcher distributes its
    settings),
    machines pausing are left out of both parts; under MDM distribution every machine's pause is listed.
    When the response is truncated, changes that still hold are kept first, a machine's own before
    changes the
    organization made to every machine (a mode change other than a pause, an agent locked off). An
    unknown
    `installation_id` lists nothing. Other people's email addresses are hidden unless you may read user
    emails. The organization-wide feed is reused for up to 5 minutes, so it can be that old
    (`generated_at` says
    when it was computed); one machine's feed is computed for each request.

    Args:
        installation_id (None | Unset | UUID): One machine, whose full 7 days are listed; omit for
            the organization-wide feed.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[AgentInventoryActivityResponse | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        installation_id=installation_id,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient | Client,
    installation_id: None | Unset | UUID = UNSET,
) -> AgentInventoryActivityResponse | HTTPValidationError | None:
    """List Agent Inventory Activity Endpoint

     List what changed on machines running the Watcher client in the last 7 days, newest first.

    Changes are found by comparing the reports each machine's client sent one after another: check-ins
    stopping,
    client updates, agents turned off or on, Watcher's hooks going missing or coming back, snoozes,
    enforcement
    mode changes and upload backlogs. For one machine (`installation_id`), every change in the 7 days.
    For the whole
    organization, the changes in the last 24 hours (`recent_since`) except check-ins stopping (the
    machine list's
    check-in state shows those), plus earlier changes that still hold when the machine's reports say
    when they
    began: an agent turned off, a turned-on agent's hooks missing, an active snooze, uploads backing up
    and grading
    paused. While the organization's own mode is paused (known only when Watcher distributes its
    settings),
    machines pausing are left out of both parts; under MDM distribution every machine's pause is listed.
    When the response is truncated, changes that still hold are kept first, a machine's own before
    changes the
    organization made to every machine (a mode change other than a pause, an agent locked off). An
    unknown
    `installation_id` lists nothing. Other people's email addresses are hidden unless you may read user
    emails. The organization-wide feed is reused for up to 5 minutes, so it can be that old
    (`generated_at` says
    when it was computed); one machine's feed is computed for each request.

    Args:
        installation_id (None | Unset | UUID): One machine, whose full 7 days are listed; omit for
            the organization-wide feed.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        AgentInventoryActivityResponse | HTTPValidationError
    """

    return sync_detailed(
        client=client,
        installation_id=installation_id,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient | Client,
    installation_id: None | Unset | UUID = UNSET,
) -> Response[AgentInventoryActivityResponse | HTTPValidationError]:
    """List Agent Inventory Activity Endpoint

     List what changed on machines running the Watcher client in the last 7 days, newest first.

    Changes are found by comparing the reports each machine's client sent one after another: check-ins
    stopping,
    client updates, agents turned off or on, Watcher's hooks going missing or coming back, snoozes,
    enforcement
    mode changes and upload backlogs. For one machine (`installation_id`), every change in the 7 days.
    For the whole
    organization, the changes in the last 24 hours (`recent_since`) except check-ins stopping (the
    machine list's
    check-in state shows those), plus earlier changes that still hold when the machine's reports say
    when they
    began: an agent turned off, a turned-on agent's hooks missing, an active snooze, uploads backing up
    and grading
    paused. While the organization's own mode is paused (known only when Watcher distributes its
    settings),
    machines pausing are left out of both parts; under MDM distribution every machine's pause is listed.
    When the response is truncated, changes that still hold are kept first, a machine's own before
    changes the
    organization made to every machine (a mode change other than a pause, an agent locked off). An
    unknown
    `installation_id` lists nothing. Other people's email addresses are hidden unless you may read user
    emails. The organization-wide feed is reused for up to 5 minutes, so it can be that old
    (`generated_at` says
    when it was computed); one machine's feed is computed for each request.

    Args:
        installation_id (None | Unset | UUID): One machine, whose full 7 days are listed; omit for
            the organization-wide feed.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[AgentInventoryActivityResponse | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        installation_id=installation_id,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient | Client,
    installation_id: None | Unset | UUID = UNSET,
) -> AgentInventoryActivityResponse | HTTPValidationError | None:
    """List Agent Inventory Activity Endpoint

     List what changed on machines running the Watcher client in the last 7 days, newest first.

    Changes are found by comparing the reports each machine's client sent one after another: check-ins
    stopping,
    client updates, agents turned off or on, Watcher's hooks going missing or coming back, snoozes,
    enforcement
    mode changes and upload backlogs. For one machine (`installation_id`), every change in the 7 days.
    For the whole
    organization, the changes in the last 24 hours (`recent_since`) except check-ins stopping (the
    machine list's
    check-in state shows those), plus earlier changes that still hold when the machine's reports say
    when they
    began: an agent turned off, a turned-on agent's hooks missing, an active snooze, uploads backing up
    and grading
    paused. While the organization's own mode is paused (known only when Watcher distributes its
    settings),
    machines pausing are left out of both parts; under MDM distribution every machine's pause is listed.
    When the response is truncated, changes that still hold are kept first, a machine's own before
    changes the
    organization made to every machine (a mode change other than a pause, an agent locked off). An
    unknown
    `installation_id` lists nothing. Other people's email addresses are hidden unless you may read user
    emails. The organization-wide feed is reused for up to 5 minutes, so it can be that old
    (`generated_at` says
    when it was computed); one machine's feed is computed for each request.

    Args:
        installation_id (None | Unset | UUID): One machine, whose full 7 days are listed; omit for
            the organization-wide feed.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        AgentInventoryActivityResponse | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            client=client,
            installation_id=installation_id,
        )
    ).parsed
