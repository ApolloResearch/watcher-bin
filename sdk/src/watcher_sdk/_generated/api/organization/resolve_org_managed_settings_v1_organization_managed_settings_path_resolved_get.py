from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.org_managed_settings_resolved import OrgManagedSettingsResolved
from ...types import Response


def _get_kwargs(
    path: str,
) -> dict[str, Any]:

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/v1/organization/managed-settings/{path}/resolved".format(
            path=quote(str(path), safe=""),
        ),
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> HTTPValidationError | OrgManagedSettingsResolved | None:
    if response.status_code == 200:
        response_200 = OrgManagedSettingsResolved.from_dict(response.json())

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
) -> Response[HTTPValidationError | OrgManagedSettingsResolved]:
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
) -> Response[HTTPValidationError | OrgManagedSettingsResolved]:
    r"""Resolve Org Managed Settings

     Return the document machines should apply for this path, or 404 when unmanaged.

    Any authenticated member of the org can read this (machines authenticate
    with per-user credentials, so a member JWT need not carry the admin-only
    settings permission). An org or user API key is the exception: it must carry
    org:settings:read, the same slug the other settings routes enforce. 404
    covers both \"the org distributes via MDM\" and \"no document saved yet\";
    clients treat it as \"no managed settings\" and keep their last-known-good
    file. That expected 404 carries a structured detail
    (``{\"code\": \"no_managed_settings\", \"message\": ...}``) so clients can tell
    it apart from a routing-layer 404 (e.g. an older server without this
    route), whose body is a plain string.

    Args:
        path (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | OrgManagedSettingsResolved]
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
) -> HTTPValidationError | OrgManagedSettingsResolved | None:
    r"""Resolve Org Managed Settings

     Return the document machines should apply for this path, or 404 when unmanaged.

    Any authenticated member of the org can read this (machines authenticate
    with per-user credentials, so a member JWT need not carry the admin-only
    settings permission). An org or user API key is the exception: it must carry
    org:settings:read, the same slug the other settings routes enforce. 404
    covers both \"the org distributes via MDM\" and \"no document saved yet\";
    clients treat it as \"no managed settings\" and keep their last-known-good
    file. That expected 404 carries a structured detail
    (``{\"code\": \"no_managed_settings\", \"message\": ...}``) so clients can tell
    it apart from a routing-layer 404 (e.g. an older server without this
    route), whose body is a plain string.

    Args:
        path (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | OrgManagedSettingsResolved
    """

    return sync_detailed(
        path=path,
        client=client,
    ).parsed


async def asyncio_detailed(
    path: str,
    *,
    client: AuthenticatedClient | Client,
) -> Response[HTTPValidationError | OrgManagedSettingsResolved]:
    r"""Resolve Org Managed Settings

     Return the document machines should apply for this path, or 404 when unmanaged.

    Any authenticated member of the org can read this (machines authenticate
    with per-user credentials, so a member JWT need not carry the admin-only
    settings permission). An org or user API key is the exception: it must carry
    org:settings:read, the same slug the other settings routes enforce. 404
    covers both \"the org distributes via MDM\" and \"no document saved yet\";
    clients treat it as \"no managed settings\" and keep their last-known-good
    file. That expected 404 carries a structured detail
    (``{\"code\": \"no_managed_settings\", \"message\": ...}``) so clients can tell
    it apart from a routing-layer 404 (e.g. an older server without this
    route), whose body is a plain string.

    Args:
        path (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | OrgManagedSettingsResolved]
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
) -> HTTPValidationError | OrgManagedSettingsResolved | None:
    r"""Resolve Org Managed Settings

     Return the document machines should apply for this path, or 404 when unmanaged.

    Any authenticated member of the org can read this (machines authenticate
    with per-user credentials, so a member JWT need not carry the admin-only
    settings permission). An org or user API key is the exception: it must carry
    org:settings:read, the same slug the other settings routes enforce. 404
    covers both \"the org distributes via MDM\" and \"no document saved yet\";
    clients treat it as \"no managed settings\" and keep their last-known-good
    file. That expected 404 carries a structured detail
    (``{\"code\": \"no_managed_settings\", \"message\": ...}``) so clients can tell
    it apart from a routing-layer 404 (e.g. an older server without this
    route), whose body is a plain string.

    Args:
        path (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | OrgManagedSettingsResolved
    """

    return (
        await asyncio_detailed(
            path=path,
            client=client,
        )
    ).parsed
