from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.agent_inventory_user_list_response import AgentInventoryUserListResponse
from ...models.http_validation_error import HTTPValidationError
from ...models.list_agent_inventory_users_endpoint_v1_agent_inventory_users_get_coverage_type_0 import (
    ListAgentInventoryUsersEndpointV1AgentInventoryUsersGetCoverageType0,
)
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    agent: list[str] | None | Unset = UNSET,
    coverage: ListAgentInventoryUsersEndpointV1AgentInventoryUsersGetCoverageType0
    | None
    | Unset = UNSET,
    reporting: bool | None | Unset = UNSET,
    key: None | str | Unset = UNSET,
    limit: int | Unset = 50,
    offset: int | Unset = 0,
) -> dict[str, Any]:

    params: dict[str, Any] = {}

    json_agent: list[str] | None | Unset
    if isinstance(agent, Unset):
        json_agent = UNSET
    elif isinstance(agent, list):
        json_agent = agent

    else:
        json_agent = agent
    params["agent"] = json_agent

    json_coverage: None | str | Unset
    if isinstance(coverage, Unset):
        json_coverage = UNSET
    elif isinstance(
        coverage, ListAgentInventoryUsersEndpointV1AgentInventoryUsersGetCoverageType0
    ):
        json_coverage = coverage.value
    else:
        json_coverage = coverage
    params["coverage"] = json_coverage

    json_reporting: bool | None | Unset
    if isinstance(reporting, Unset):
        json_reporting = UNSET
    else:
        json_reporting = reporting
    params["reporting"] = json_reporting

    json_key: None | str | Unset
    if isinstance(key, Unset):
        json_key = UNSET
    else:
        json_key = key
    params["key"] = json_key

    params["limit"] = limit

    params["offset"] = offset

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/v1/agent-inventory/users",
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> AgentInventoryUserListResponse | HTTPValidationError | None:
    if response.status_code == 200:
        response_200 = AgentInventoryUserListResponse.from_dict(response.json())

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
) -> Response[AgentInventoryUserListResponse | HTTPValidationError]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient | Client,
    agent: list[str] | None | Unset = UNSET,
    coverage: ListAgentInventoryUsersEndpointV1AgentInventoryUsersGetCoverageType0
    | None
    | Unset = UNSET,
    reporting: bool | None | Unset = UNSET,
    key: None | str | Unset = UNSET,
    limit: int | Unset = 50,
    offset: int | Unset = 0,
) -> Response[AgentInventoryUserListResponse | HTTPValidationError]:
    """List Agent Inventory Users Endpoint

     List people seen in the last 7 days, with their machines and the agents they used, most recently
    active first.

    Other people's email addresses are hidden unless you may read user emails; a person a gateway named
    is a
    Watcher user whose email is the login the gateway reported. Dates are UTC dates.

    Args:
        agent (list[str] | None | Unset): People who used any of these agents in the last 7 days,
            and `unrecognized` for any unrecognized gateway client; repeat the parameter for each.
        coverage (ListAgentInventoryUsersEndpointV1AgentInventoryUsersGetCoverageType0 | None |
            Unset): People with this coverage for one of the `agent` values, or for any agent.
        reporting (bool | None | Unset): True: people with a machine that reported in the last 7
            days; false: others.
        key (None | str | Unset): One person, by the `key` from this list.
        limit (int | Unset):  Default: 50.
        offset (int | Unset):  Default: 0.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[AgentInventoryUserListResponse | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        agent=agent,
        coverage=coverage,
        reporting=reporting,
        key=key,
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
    agent: list[str] | None | Unset = UNSET,
    coverage: ListAgentInventoryUsersEndpointV1AgentInventoryUsersGetCoverageType0
    | None
    | Unset = UNSET,
    reporting: bool | None | Unset = UNSET,
    key: None | str | Unset = UNSET,
    limit: int | Unset = 50,
    offset: int | Unset = 0,
) -> AgentInventoryUserListResponse | HTTPValidationError | None:
    """List Agent Inventory Users Endpoint

     List people seen in the last 7 days, with their machines and the agents they used, most recently
    active first.

    Other people's email addresses are hidden unless you may read user emails; a person a gateway named
    is a
    Watcher user whose email is the login the gateway reported. Dates are UTC dates.

    Args:
        agent (list[str] | None | Unset): People who used any of these agents in the last 7 days,
            and `unrecognized` for any unrecognized gateway client; repeat the parameter for each.
        coverage (ListAgentInventoryUsersEndpointV1AgentInventoryUsersGetCoverageType0 | None |
            Unset): People with this coverage for one of the `agent` values, or for any agent.
        reporting (bool | None | Unset): True: people with a machine that reported in the last 7
            days; false: others.
        key (None | str | Unset): One person, by the `key` from this list.
        limit (int | Unset):  Default: 50.
        offset (int | Unset):  Default: 0.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        AgentInventoryUserListResponse | HTTPValidationError
    """

    return sync_detailed(
        client=client,
        agent=agent,
        coverage=coverage,
        reporting=reporting,
        key=key,
        limit=limit,
        offset=offset,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient | Client,
    agent: list[str] | None | Unset = UNSET,
    coverage: ListAgentInventoryUsersEndpointV1AgentInventoryUsersGetCoverageType0
    | None
    | Unset = UNSET,
    reporting: bool | None | Unset = UNSET,
    key: None | str | Unset = UNSET,
    limit: int | Unset = 50,
    offset: int | Unset = 0,
) -> Response[AgentInventoryUserListResponse | HTTPValidationError]:
    """List Agent Inventory Users Endpoint

     List people seen in the last 7 days, with their machines and the agents they used, most recently
    active first.

    Other people's email addresses are hidden unless you may read user emails; a person a gateway named
    is a
    Watcher user whose email is the login the gateway reported. Dates are UTC dates.

    Args:
        agent (list[str] | None | Unset): People who used any of these agents in the last 7 days,
            and `unrecognized` for any unrecognized gateway client; repeat the parameter for each.
        coverage (ListAgentInventoryUsersEndpointV1AgentInventoryUsersGetCoverageType0 | None |
            Unset): People with this coverage for one of the `agent` values, or for any agent.
        reporting (bool | None | Unset): True: people with a machine that reported in the last 7
            days; false: others.
        key (None | str | Unset): One person, by the `key` from this list.
        limit (int | Unset):  Default: 50.
        offset (int | Unset):  Default: 0.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[AgentInventoryUserListResponse | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        agent=agent,
        coverage=coverage,
        reporting=reporting,
        key=key,
        limit=limit,
        offset=offset,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient | Client,
    agent: list[str] | None | Unset = UNSET,
    coverage: ListAgentInventoryUsersEndpointV1AgentInventoryUsersGetCoverageType0
    | None
    | Unset = UNSET,
    reporting: bool | None | Unset = UNSET,
    key: None | str | Unset = UNSET,
    limit: int | Unset = 50,
    offset: int | Unset = 0,
) -> AgentInventoryUserListResponse | HTTPValidationError | None:
    """List Agent Inventory Users Endpoint

     List people seen in the last 7 days, with their machines and the agents they used, most recently
    active first.

    Other people's email addresses are hidden unless you may read user emails; a person a gateway named
    is a
    Watcher user whose email is the login the gateway reported. Dates are UTC dates.

    Args:
        agent (list[str] | None | Unset): People who used any of these agents in the last 7 days,
            and `unrecognized` for any unrecognized gateway client; repeat the parameter for each.
        coverage (ListAgentInventoryUsersEndpointV1AgentInventoryUsersGetCoverageType0 | None |
            Unset): People with this coverage for one of the `agent` values, or for any agent.
        reporting (bool | None | Unset): True: people with a machine that reported in the last 7
            days; false: others.
        key (None | str | Unset): One person, by the `key` from this list.
        limit (int | Unset):  Default: 50.
        offset (int | Unset):  Default: 0.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        AgentInventoryUserListResponse | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            client=client,
            agent=agent,
            coverage=coverage,
            reporting=reporting,
            key=key,
            limit=limit,
            offset=offset,
        )
    ).parsed
