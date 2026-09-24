from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.org_managed_settings_doc import OrgManagedSettingsDoc
from ...models.org_managed_settings_update import OrgManagedSettingsUpdate
from ...types import Response


def _get_kwargs(
    path: str,
    *,
    body: OrgManagedSettingsUpdate,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

    _kwargs: dict[str, Any] = {
        "method": "put",
        "url": "/v1/organization/managed-settings/{path}".format(
            path=quote(str(path), safe=""),
        ),
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
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
    body: OrgManagedSettingsUpdate,
) -> Response[HTTPValidationError | OrgManagedSettingsDoc]:
    """Update Org Managed Settings

     Validate and save a new version of the org's managed settings document.

    The document is validated against the Watcher settings schema (merged onto
    the builtin defaults, exactly as machines will apply it); an invalid
    document returns 422 with the field and value errors and stores nothing.
    This endpoint is also the programmatic write path: an org API key with the
    write permission can call it from CI.

    Args:
        path (str):
        body (OrgManagedSettingsUpdate): Request body to save a new version of the org's managed
            Watcher Live settings document.

            Body for PUT /v1/organization/managed-settings/{path}.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | OrgManagedSettingsDoc]
    """

    kwargs = _get_kwargs(
        path=path,
        body=body,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    path: str,
    *,
    client: AuthenticatedClient | Client,
    body: OrgManagedSettingsUpdate,
) -> HTTPValidationError | OrgManagedSettingsDoc | None:
    """Update Org Managed Settings

     Validate and save a new version of the org's managed settings document.

    The document is validated against the Watcher settings schema (merged onto
    the builtin defaults, exactly as machines will apply it); an invalid
    document returns 422 with the field and value errors and stores nothing.
    This endpoint is also the programmatic write path: an org API key with the
    write permission can call it from CI.

    Args:
        path (str):
        body (OrgManagedSettingsUpdate): Request body to save a new version of the org's managed
            Watcher Live settings document.

            Body for PUT /v1/organization/managed-settings/{path}.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | OrgManagedSettingsDoc
    """

    return sync_detailed(
        path=path,
        client=client,
        body=body,
    ).parsed


async def asyncio_detailed(
    path: str,
    *,
    client: AuthenticatedClient | Client,
    body: OrgManagedSettingsUpdate,
) -> Response[HTTPValidationError | OrgManagedSettingsDoc]:
    """Update Org Managed Settings

     Validate and save a new version of the org's managed settings document.

    The document is validated against the Watcher settings schema (merged onto
    the builtin defaults, exactly as machines will apply it); an invalid
    document returns 422 with the field and value errors and stores nothing.
    This endpoint is also the programmatic write path: an org API key with the
    write permission can call it from CI.

    Args:
        path (str):
        body (OrgManagedSettingsUpdate): Request body to save a new version of the org's managed
            Watcher Live settings document.

            Body for PUT /v1/organization/managed-settings/{path}.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | OrgManagedSettingsDoc]
    """

    kwargs = _get_kwargs(
        path=path,
        body=body,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    path: str,
    *,
    client: AuthenticatedClient | Client,
    body: OrgManagedSettingsUpdate,
) -> HTTPValidationError | OrgManagedSettingsDoc | None:
    """Update Org Managed Settings

     Validate and save a new version of the org's managed settings document.

    The document is validated against the Watcher settings schema (merged onto
    the builtin defaults, exactly as machines will apply it); an invalid
    document returns 422 with the field and value errors and stores nothing.
    This endpoint is also the programmatic write path: an org API key with the
    write permission can call it from CI.

    Args:
        path (str):
        body (OrgManagedSettingsUpdate): Request body to save a new version of the org's managed
            Watcher Live settings document.

            Body for PUT /v1/organization/managed-settings/{path}.

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
            body=body,
        )
    ).parsed
