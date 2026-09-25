from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.org_settings import OrgSettings
from ...models.org_settings_update import OrgSettingsUpdate
from ...types import Response


def _get_kwargs(
    *,
    body: OrgSettingsUpdate,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

    _kwargs: dict[str, Any] = {
        "method": "patch",
        "url": "/v1/organization/settings",
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> HTTPValidationError | OrgSettings | None:
    if response.status_code == 200:
        response_200 = OrgSettings.from_dict(response.json())

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
) -> Response[HTTPValidationError | OrgSettings]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient | Client,
    body: OrgSettingsUpdate,
) -> Response[HTTPValidationError | OrgSettings]:
    """Update Org Settings

     Update organization settings.

    Fields omitted from the body are left unchanged; fields sent as null are
    cleared. Null is only accepted for clearable fields; null on any other
    field returns 400. The Slack webhook URL is encrypted at rest on deployments
    with encryption configured (Watcher Cloud is) and stored as supplied
    otherwise. It is clearable via null, unless the deployment supplies it
    through `SLACK_WEBHOOK_URL`, in which case any body mentioning
    `slack_webhook_url` is refused whole with a 409.

    Args:
        body (OrgSettingsUpdate): Request body for PATCH /v1/org/settings.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | OrgSettings]
    """

    kwargs = _get_kwargs(
        body=body,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient | Client,
    body: OrgSettingsUpdate,
) -> HTTPValidationError | OrgSettings | None:
    """Update Org Settings

     Update organization settings.

    Fields omitted from the body are left unchanged; fields sent as null are
    cleared. Null is only accepted for clearable fields; null on any other
    field returns 400. The Slack webhook URL is encrypted at rest on deployments
    with encryption configured (Watcher Cloud is) and stored as supplied
    otherwise. It is clearable via null, unless the deployment supplies it
    through `SLACK_WEBHOOK_URL`, in which case any body mentioning
    `slack_webhook_url` is refused whole with a 409.

    Args:
        body (OrgSettingsUpdate): Request body for PATCH /v1/org/settings.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | OrgSettings
    """

    return sync_detailed(
        client=client,
        body=body,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient | Client,
    body: OrgSettingsUpdate,
) -> Response[HTTPValidationError | OrgSettings]:
    """Update Org Settings

     Update organization settings.

    Fields omitted from the body are left unchanged; fields sent as null are
    cleared. Null is only accepted for clearable fields; null on any other
    field returns 400. The Slack webhook URL is encrypted at rest on deployments
    with encryption configured (Watcher Cloud is) and stored as supplied
    otherwise. It is clearable via null, unless the deployment supplies it
    through `SLACK_WEBHOOK_URL`, in which case any body mentioning
    `slack_webhook_url` is refused whole with a 409.

    Args:
        body (OrgSettingsUpdate): Request body for PATCH /v1/org/settings.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | OrgSettings]
    """

    kwargs = _get_kwargs(
        body=body,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient | Client,
    body: OrgSettingsUpdate,
) -> HTTPValidationError | OrgSettings | None:
    """Update Org Settings

     Update organization settings.

    Fields omitted from the body are left unchanged; fields sent as null are
    cleared. Null is only accepted for clearable fields; null on any other
    field returns 400. The Slack webhook URL is encrypted at rest on deployments
    with encryption configured (Watcher Cloud is) and stored as supplied
    otherwise. It is clearable via null, unless the deployment supplies it
    through `SLACK_WEBHOOK_URL`, in which case any body mentioning
    `slack_webhook_url` is refused whole with a 409.

    Args:
        body (OrgSettingsUpdate): Request body for PATCH /v1/org/settings.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | OrgSettings
    """

    return (
        await asyncio_detailed(
            client=client,
            body=body,
        )
    ).parsed
