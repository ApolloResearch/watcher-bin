from http import HTTPStatus
from typing import Any
from urllib.parse import quote
from uuid import UUID

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.agent_inventory_installation_removal_response import (
    AgentInventoryInstallationRemovalResponse,
)
from ...models.http_validation_error import HTTPValidationError
from ...models.installation_report_error_response import InstallationReportErrorResponse
from ...types import Response


def _get_kwargs(
    installation_id: UUID,
) -> dict[str, Any]:

    _kwargs: dict[str, Any] = {
        "method": "delete",
        "url": "/v1/agent-inventory/installations/{installation_id}".format(
            installation_id=quote(str(installation_id), safe=""),
        ),
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> (
    AgentInventoryInstallationRemovalResponse
    | HTTPValidationError
    | InstallationReportErrorResponse
    | None
):
    if response.status_code == 200:
        response_200 = AgentInventoryInstallationRemovalResponse.from_dict(
            response.json()
        )

        return response_200

    if response.status_code == 404:
        response_404 = InstallationReportErrorResponse.from_dict(response.json())

        return response_404

    if response.status_code == 409:
        response_409 = InstallationReportErrorResponse.from_dict(response.json())

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
) -> Response[
    AgentInventoryInstallationRemovalResponse
    | HTTPValidationError
    | InstallationReportErrorResponse
]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    installation_id: UUID,
    *,
    client: AuthenticatedClient | Client,
) -> Response[
    AgentInventoryInstallationRemovalResponse
    | HTTPValidationError
    | InstallationReportErrorResponse
]:
    """Remove Agent Inventory Installation Endpoint

     Remove an offline machine from the agent inventory, such as a departed person's laptop or a retired
    machine.

    The machine disappears from the machine and people lists, the summary's counts and the activity
    feed. Nothing is
    deleted: its reports stay stored, and if its Watcher client reports again the machine is listed
    again with its
    history. Removing a machine that is already removed and has not reported since changes nothing and
    returns
    `already_removed`. Only a machine that is not online can be removed.

    Args:
        installation_id (UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[AgentInventoryInstallationRemovalResponse | HTTPValidationError | InstallationReportErrorResponse]
    """

    kwargs = _get_kwargs(
        installation_id=installation_id,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    installation_id: UUID,
    *,
    client: AuthenticatedClient | Client,
) -> (
    AgentInventoryInstallationRemovalResponse
    | HTTPValidationError
    | InstallationReportErrorResponse
    | None
):
    """Remove Agent Inventory Installation Endpoint

     Remove an offline machine from the agent inventory, such as a departed person's laptop or a retired
    machine.

    The machine disappears from the machine and people lists, the summary's counts and the activity
    feed. Nothing is
    deleted: its reports stay stored, and if its Watcher client reports again the machine is listed
    again with its
    history. Removing a machine that is already removed and has not reported since changes nothing and
    returns
    `already_removed`. Only a machine that is not online can be removed.

    Args:
        installation_id (UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        AgentInventoryInstallationRemovalResponse | HTTPValidationError | InstallationReportErrorResponse
    """

    return sync_detailed(
        installation_id=installation_id,
        client=client,
    ).parsed


async def asyncio_detailed(
    installation_id: UUID,
    *,
    client: AuthenticatedClient | Client,
) -> Response[
    AgentInventoryInstallationRemovalResponse
    | HTTPValidationError
    | InstallationReportErrorResponse
]:
    """Remove Agent Inventory Installation Endpoint

     Remove an offline machine from the agent inventory, such as a departed person's laptop or a retired
    machine.

    The machine disappears from the machine and people lists, the summary's counts and the activity
    feed. Nothing is
    deleted: its reports stay stored, and if its Watcher client reports again the machine is listed
    again with its
    history. Removing a machine that is already removed and has not reported since changes nothing and
    returns
    `already_removed`. Only a machine that is not online can be removed.

    Args:
        installation_id (UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[AgentInventoryInstallationRemovalResponse | HTTPValidationError | InstallationReportErrorResponse]
    """

    kwargs = _get_kwargs(
        installation_id=installation_id,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    installation_id: UUID,
    *,
    client: AuthenticatedClient | Client,
) -> (
    AgentInventoryInstallationRemovalResponse
    | HTTPValidationError
    | InstallationReportErrorResponse
    | None
):
    """Remove Agent Inventory Installation Endpoint

     Remove an offline machine from the agent inventory, such as a departed person's laptop or a retired
    machine.

    The machine disappears from the machine and people lists, the summary's counts and the activity
    feed. Nothing is
    deleted: its reports stay stored, and if its Watcher client reports again the machine is listed
    again with its
    history. Removing a machine that is already removed and has not reported since changes nothing and
    returns
    `already_removed`. Only a machine that is not online can be removed.

    Args:
        installation_id (UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        AgentInventoryInstallationRemovalResponse | HTTPValidationError | InstallationReportErrorResponse
    """

    return (
        await asyncio_detailed(
            installation_id=installation_id,
            client=client,
        )
    ).parsed
