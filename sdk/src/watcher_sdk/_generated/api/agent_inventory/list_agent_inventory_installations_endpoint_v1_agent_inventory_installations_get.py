from http import HTTPStatus
from typing import Any
from uuid import UUID

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.agent_inventory_installation_list_response import (
    AgentInventoryInstallationListResponse,
)
from ...models.http_validation_error import HTTPValidationError
from ...models.list_agent_inventory_installations_endpoint_v1_agent_inventory_installations_get_coverage_type_0 import (
    ListAgentInventoryInstallationsEndpointV1AgentInventoryInstallationsGetCoverageType0,
)
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    agent: None | str | Unset = UNSET,
    coverage: ListAgentInventoryInstallationsEndpointV1AgentInventoryInstallationsGetCoverageType0
    | None
    | Unset = UNSET,
    installation_id: None | Unset | UUID = UNSET,
    user_id: None | Unset | UUID = UNSET,
    limit: int | Unset = 50,
    offset: int | Unset = 0,
) -> dict[str, Any]:

    params: dict[str, Any] = {}

    json_agent: None | str | Unset
    if isinstance(agent, Unset):
        json_agent = UNSET
    else:
        json_agent = agent
    params["agent"] = json_agent

    json_coverage: None | str | Unset
    if isinstance(coverage, Unset):
        json_coverage = UNSET
    elif isinstance(
        coverage,
        ListAgentInventoryInstallationsEndpointV1AgentInventoryInstallationsGetCoverageType0,
    ):
        json_coverage = coverage.value
    else:
        json_coverage = coverage
    params["coverage"] = json_coverage

    json_installation_id: None | str | Unset
    if isinstance(installation_id, Unset):
        json_installation_id = UNSET
    elif isinstance(installation_id, UUID):
        json_installation_id = str(installation_id)
    else:
        json_installation_id = installation_id
    params["installation_id"] = json_installation_id

    json_user_id: None | str | Unset
    if isinstance(user_id, Unset):
        json_user_id = UNSET
    elif isinstance(user_id, UUID):
        json_user_id = str(user_id)
    else:
        json_user_id = user_id
    params["user_id"] = json_user_id

    params["limit"] = limit

    params["offset"] = offset

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/v1/agent-inventory/installations",
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> AgentInventoryInstallationListResponse | HTTPValidationError | None:
    if response.status_code == 200:
        response_200 = AgentInventoryInstallationListResponse.from_dict(response.json())

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
) -> Response[AgentInventoryInstallationListResponse | HTTPValidationError]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient | Client,
    agent: None | str | Unset = UNSET,
    coverage: ListAgentInventoryInstallationsEndpointV1AgentInventoryInstallationsGetCoverageType0
    | None
    | Unset = UNSET,
    installation_id: None | Unset | UUID = UNSET,
    user_id: None | Unset | UUID = UNSET,
    limit: int | Unset = 50,
    offset: int | Unset = 0,
) -> Response[AgentInventoryInstallationListResponse | HTTPValidationError]:
    """List Agent Inventory Installations Endpoint

     List machines running the Watcher client, with their owner and agents, most recently reported first.

    Other people's email addresses are hidden unless you may read user emails. Dates are UTC dates.

    Args:
        agent (None | str | Unset): Machines with this agent.
        coverage
            (ListAgentInventoryInstallationsEndpointV1AgentInventoryInstallationsGetCoverageType0 |
            None | Unset): Machines with an agent in this coverage state.
        installation_id (None | Unset | UUID): One machine.
        user_id (None | Unset | UUID): Machines this person owns.
        limit (int | Unset):  Default: 50.
        offset (int | Unset):  Default: 0.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[AgentInventoryInstallationListResponse | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        agent=agent,
        coverage=coverage,
        installation_id=installation_id,
        user_id=user_id,
        limit=limit,
        offset=offset,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient | Client,
    agent: None | str | Unset = UNSET,
    coverage: ListAgentInventoryInstallationsEndpointV1AgentInventoryInstallationsGetCoverageType0
    | None
    | Unset = UNSET,
    installation_id: None | Unset | UUID = UNSET,
    user_id: None | Unset | UUID = UNSET,
    limit: int | Unset = 50,
    offset: int | Unset = 0,
) -> AgentInventoryInstallationListResponse | HTTPValidationError | None:
    """List Agent Inventory Installations Endpoint

     List machines running the Watcher client, with their owner and agents, most recently reported first.

    Other people's email addresses are hidden unless you may read user emails. Dates are UTC dates.

    Args:
        agent (None | str | Unset): Machines with this agent.
        coverage
            (ListAgentInventoryInstallationsEndpointV1AgentInventoryInstallationsGetCoverageType0 |
            None | Unset): Machines with an agent in this coverage state.
        installation_id (None | Unset | UUID): One machine.
        user_id (None | Unset | UUID): Machines this person owns.
        limit (int | Unset):  Default: 50.
        offset (int | Unset):  Default: 0.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        AgentInventoryInstallationListResponse | HTTPValidationError
    """

    return sync_detailed(
        client=client,
        agent=agent,
        coverage=coverage,
        installation_id=installation_id,
        user_id=user_id,
        limit=limit,
        offset=offset,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient | Client,
    agent: None | str | Unset = UNSET,
    coverage: ListAgentInventoryInstallationsEndpointV1AgentInventoryInstallationsGetCoverageType0
    | None
    | Unset = UNSET,
    installation_id: None | Unset | UUID = UNSET,
    user_id: None | Unset | UUID = UNSET,
    limit: int | Unset = 50,
    offset: int | Unset = 0,
) -> Response[AgentInventoryInstallationListResponse | HTTPValidationError]:
    """List Agent Inventory Installations Endpoint

     List machines running the Watcher client, with their owner and agents, most recently reported first.

    Other people's email addresses are hidden unless you may read user emails. Dates are UTC dates.

    Args:
        agent (None | str | Unset): Machines with this agent.
        coverage
            (ListAgentInventoryInstallationsEndpointV1AgentInventoryInstallationsGetCoverageType0 |
            None | Unset): Machines with an agent in this coverage state.
        installation_id (None | Unset | UUID): One machine.
        user_id (None | Unset | UUID): Machines this person owns.
        limit (int | Unset):  Default: 50.
        offset (int | Unset):  Default: 0.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[AgentInventoryInstallationListResponse | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        agent=agent,
        coverage=coverage,
        installation_id=installation_id,
        user_id=user_id,
        limit=limit,
        offset=offset,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient | Client,
    agent: None | str | Unset = UNSET,
    coverage: ListAgentInventoryInstallationsEndpointV1AgentInventoryInstallationsGetCoverageType0
    | None
    | Unset = UNSET,
    installation_id: None | Unset | UUID = UNSET,
    user_id: None | Unset | UUID = UNSET,
    limit: int | Unset = 50,
    offset: int | Unset = 0,
) -> AgentInventoryInstallationListResponse | HTTPValidationError | None:
    """List Agent Inventory Installations Endpoint

     List machines running the Watcher client, with their owner and agents, most recently reported first.

    Other people's email addresses are hidden unless you may read user emails. Dates are UTC dates.

    Args:
        agent (None | str | Unset): Machines with this agent.
        coverage
            (ListAgentInventoryInstallationsEndpointV1AgentInventoryInstallationsGetCoverageType0 |
            None | Unset): Machines with an agent in this coverage state.
        installation_id (None | Unset | UUID): One machine.
        user_id (None | Unset | UUID): Machines this person owns.
        limit (int | Unset):  Default: 50.
        offset (int | Unset):  Default: 0.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        AgentInventoryInstallationListResponse | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            client=client,
            agent=agent,
            coverage=coverage,
            installation_id=installation_id,
            user_id=user_id,
            limit=limit,
            offset=offset,
        )
    ).parsed
