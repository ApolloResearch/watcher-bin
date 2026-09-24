from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.org_managed_settings_doc import OrgManagedSettingsDoc
from ...types import Response


def _get_kwargs(
    path: str,
) -> dict[str, Any]:

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/v1/organization/managed-settings/{path}".format(
            path=quote(str(path), safe=""),
        ),
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> HTTPValidationError | OrgManagedSettingsDoc | None:
    if response.status_code == 200:
        response_200 = OrgManagedSettingsDoc.from_dict(response.json())

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
) -> Response[HTTPValidationError | OrgManagedSettingsDoc]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    path: str,
    *,
    client: AuthenticatedClient | Client,
) -> Response[HTTPValidationError | OrgManagedSettingsDoc]:
    """Get Org Managed Settings

     Return the org's current managed settings document for this path.

    Args:
        path (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | OrgManagedSettingsDoc]
    """

    kwargs = _get_kwargs(
        path=path,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    path: str,
    *,
    client: AuthenticatedClient | Client,
) -> HTTPValidationError | OrgManagedSettingsDoc | None:
    """Get Org Managed Settings

     Return the org's current managed settings document for this path.

    Args:
        path (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | OrgManagedSettingsDoc
    """

    return sync_detailed(
        path=path,
        client=client,
    ).parsed


async def asyncio_detailed(
    path: str,
    *,
    client: AuthenticatedClient | Client,
) -> Response[HTTPValidationError | OrgManagedSettingsDoc]:
    """Get Org Managed Settings

     Return the org's current managed settings document for this path.

    Args:
        path (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | OrgManagedSettingsDoc]
    """

    kwargs = _get_kwargs(
        path=path,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    path: str,
    *,
    client: AuthenticatedClient | Client,
) -> HTTPValidationError | OrgManagedSettingsDoc | None:
    """Get Org Managed Settings

     Return the org's current managed settings document for this path.

    Args:
        path (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | OrgManagedSettingsDoc
    """

    return (
        await asyncio_detailed(
            path=path,
            client=client,
        )
    ).parsed
