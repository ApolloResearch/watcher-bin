from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote
from uuid import UUID

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.installation_report import InstallationReport
from ...models.installation_report_error_response import InstallationReportErrorResponse
from ...models.installation_report_response import InstallationReportResponse
from ...types import Response


def _get_kwargs(
    installation_id: UUID,
    *,
    body: InstallationReport,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/v1/installations/{installation_id}/reports".format(
            installation_id=quote(str(installation_id), safe=""),
        ),
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Any | InstallationReportErrorResponse | InstallationReportResponse | None:
    if response.status_code == 200:
        response_200 = InstallationReportResponse.from_dict(response.json())

        return response_200

    if response.status_code == 201:
        response_201 = InstallationReportResponse.from_dict(response.json())

        return response_201

    if response.status_code == 409:
        response_409 = InstallationReportErrorResponse.from_dict(response.json())

        return response_409

    if response.status_code == 413:
        response_413 = cast(Any, None)
        return response_413

    if response.status_code == 422:
        response_422 = cast(Any, None)
        return response_422

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Response[Any | InstallationReportErrorResponse | InstallationReportResponse]:
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
    body: InstallationReport,
) -> Response[Any | InstallationReportErrorResponse | InstallationReportResponse]:
    """Post Installation Report Endpoint

     Store one report from a Watcher client installation.

    Send a report after every scan, with a new `report_id`; retry a failed request with the same one. A
    report whose ID is already stored changes nothing and returns 200 with `duplicate`. The installation
    is
    registered to the signed-in user on its first report, never to anything in the body. Agent IDs and
    values this server does not recognize are ignored. Organization API keys cannot report.

    Args:
        installation_id (UUID):
        body (InstallationReport): One report from a Watcher client installation.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | InstallationReportErrorResponse | InstallationReportResponse]
    """

    kwargs = _get_kwargs(
        installation_id=installation_id,
        body=body,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    installation_id: UUID,
    *,
    client: AuthenticatedClient | Client,
    body: InstallationReport,
) -> Any | InstallationReportErrorResponse | InstallationReportResponse | None:
    """Post Installation Report Endpoint

     Store one report from a Watcher client installation.

    Send a report after every scan, with a new `report_id`; retry a failed request with the same one. A
    report whose ID is already stored changes nothing and returns 200 with `duplicate`. The installation
    is
    registered to the signed-in user on its first report, never to anything in the body. Agent IDs and
    values this server does not recognize are ignored. Organization API keys cannot report.

    Args:
        installation_id (UUID):
        body (InstallationReport): One report from a Watcher client installation.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | InstallationReportErrorResponse | InstallationReportResponse
    """

    return sync_detailed(
        installation_id=installation_id,
        client=client,
        body=body,
    ).parsed


async def asyncio_detailed(
    installation_id: UUID,
    *,
    client: AuthenticatedClient | Client,
    body: InstallationReport,
) -> Response[Any | InstallationReportErrorResponse | InstallationReportResponse]:
    """Post Installation Report Endpoint

     Store one report from a Watcher client installation.

    Send a report after every scan, with a new `report_id`; retry a failed request with the same one. A
    report whose ID is already stored changes nothing and returns 200 with `duplicate`. The installation
    is
    registered to the signed-in user on its first report, never to anything in the body. Agent IDs and
    values this server does not recognize are ignored. Organization API keys cannot report.

    Args:
        installation_id (UUID):
        body (InstallationReport): One report from a Watcher client installation.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | InstallationReportErrorResponse | InstallationReportResponse]
    """

    kwargs = _get_kwargs(
        installation_id=installation_id,
        body=body,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    installation_id: UUID,
    *,
    client: AuthenticatedClient | Client,
    body: InstallationReport,
) -> Any | InstallationReportErrorResponse | InstallationReportResponse | None:
    """Post Installation Report Endpoint

     Store one report from a Watcher client installation.

    Send a report after every scan, with a new `report_id`; retry a failed request with the same one. A
    report whose ID is already stored changes nothing and returns 200 with `duplicate`. The installation
    is
    registered to the signed-in user on its first report, never to anything in the body. Agent IDs and
    values this server does not recognize are ignored. Organization API keys cannot report.

    Args:
        installation_id (UUID):
        body (InstallationReport): One report from a Watcher client installation.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | InstallationReportErrorResponse | InstallationReportResponse
    """

    return (
        await asyncio_detailed(
            installation_id=installation_id,
            client=client,
            body=body,
        )
    ).parsed
