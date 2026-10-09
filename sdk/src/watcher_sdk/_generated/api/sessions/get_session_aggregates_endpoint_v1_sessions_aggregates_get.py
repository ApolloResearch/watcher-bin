import datetime
from http import HTTPStatus
from typing import Any
from uuid import UUID

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.get_session_aggregates_endpoint_v1_sessions_aggregates_get_bucket import (
    GetSessionAggregatesEndpointV1SessionsAggregatesGetBucket,
)
from ...models.get_session_aggregates_endpoint_v1_sessions_aggregates_get_severity_threshold import (
    GetSessionAggregatesEndpointV1SessionsAggregatesGetSeverityThreshold,
)
from ...models.http_validation_error import HTTPValidationError
from ...models.session_aggregates_response import SessionAggregatesResponse
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    start_date: datetime.datetime | None | Unset = UNSET,
    end_date: datetime.datetime | None | Unset = UNSET,
    bucket: GetSessionAggregatesEndpointV1SessionsAggregatesGetBucket
    | Unset = GetSessionAggregatesEndpointV1SessionsAggregatesGetBucket.DAY,
    severity_threshold: GetSessionAggregatesEndpointV1SessionsAggregatesGetSeverityThreshold,
    user_id: None | Unset | UUID = UNSET,
) -> dict[str, Any]:

    params: dict[str, Any] = {}

    json_start_date: None | str | Unset
    if isinstance(start_date, Unset):
        json_start_date = UNSET
    elif isinstance(start_date, datetime.datetime):
        json_start_date = start_date.isoformat()
    else:
        json_start_date = start_date
    params["start_date"] = json_start_date

    json_end_date: None | str | Unset
    if isinstance(end_date, Unset):
        json_end_date = UNSET
    elif isinstance(end_date, datetime.datetime):
        json_end_date = end_date.isoformat()
    else:
        json_end_date = end_date
    params["end_date"] = json_end_date

    json_bucket: str | Unset = UNSET
    if not isinstance(bucket, Unset):
        json_bucket = bucket.value

    params["bucket"] = json_bucket

    json_severity_threshold = severity_threshold.value
    params["severity_threshold"] = json_severity_threshold

    json_user_id: None | str | Unset
    if isinstance(user_id, Unset):
        json_user_id = UNSET
    elif isinstance(user_id, UUID):
        json_user_id = str(user_id)
    else:
        json_user_id = user_id
    params["user_id"] = json_user_id

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/v1/sessions/aggregates",
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> HTTPValidationError | SessionAggregatesResponse | None:
    if response.status_code == 200:
        response_200 = SessionAggregatesResponse.from_dict(response.json())

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
) -> Response[HTTPValidationError | SessionAggregatesResponse]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient | Client,
    start_date: datetime.datetime | None | Unset = UNSET,
    end_date: datetime.datetime | None | Unset = UNSET,
    bucket: GetSessionAggregatesEndpointV1SessionsAggregatesGetBucket
    | Unset = GetSessionAggregatesEndpointV1SessionsAggregatesGetBucket.DAY,
    severity_threshold: GetSessionAggregatesEndpointV1SessionsAggregatesGetSeverityThreshold,
    user_id: None | Unset | UUID = UNSET,
) -> Response[HTTPValidationError | SessionAggregatesResponse]:
    """Get Session Aggregates Endpoint

     Return organization-wide aggregate session metrics, optionally filtered by owner.

    Requires ``sessions:aggregates:read:any`` through a role or credential grant,
    including when filtering to the caller's own ``user_id``. Otherwise returns HTTP 403.

    Args:
        start_date (datetime.datetime | None | Unset):
        end_date (datetime.datetime | None | Unset):
        bucket (GetSessionAggregatesEndpointV1SessionsAggregatesGetBucket | Unset):  Default:
            GetSessionAggregatesEndpointV1SessionsAggregatesGetBucket.DAY.
        severity_threshold (GetSessionAggregatesEndpointV1SessionsAggregatesGetSeverityThreshold):
        user_id (None | Unset | UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | SessionAggregatesResponse]
    """

    kwargs = _get_kwargs(
        start_date=start_date,
        end_date=end_date,
        bucket=bucket,
        severity_threshold=severity_threshold,
        user_id=user_id,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient | Client,
    start_date: datetime.datetime | None | Unset = UNSET,
    end_date: datetime.datetime | None | Unset = UNSET,
    bucket: GetSessionAggregatesEndpointV1SessionsAggregatesGetBucket
    | Unset = GetSessionAggregatesEndpointV1SessionsAggregatesGetBucket.DAY,
    severity_threshold: GetSessionAggregatesEndpointV1SessionsAggregatesGetSeverityThreshold,
    user_id: None | Unset | UUID = UNSET,
) -> HTTPValidationError | SessionAggregatesResponse | None:
    """Get Session Aggregates Endpoint

     Return organization-wide aggregate session metrics, optionally filtered by owner.

    Requires ``sessions:aggregates:read:any`` through a role or credential grant,
    including when filtering to the caller's own ``user_id``. Otherwise returns HTTP 403.

    Args:
        start_date (datetime.datetime | None | Unset):
        end_date (datetime.datetime | None | Unset):
        bucket (GetSessionAggregatesEndpointV1SessionsAggregatesGetBucket | Unset):  Default:
            GetSessionAggregatesEndpointV1SessionsAggregatesGetBucket.DAY.
        severity_threshold (GetSessionAggregatesEndpointV1SessionsAggregatesGetSeverityThreshold):
        user_id (None | Unset | UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | SessionAggregatesResponse
    """

    return sync_detailed(
        client=client,
        start_date=start_date,
        end_date=end_date,
        bucket=bucket,
        severity_threshold=severity_threshold,
        user_id=user_id,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient | Client,
    start_date: datetime.datetime | None | Unset = UNSET,
    end_date: datetime.datetime | None | Unset = UNSET,
    bucket: GetSessionAggregatesEndpointV1SessionsAggregatesGetBucket
    | Unset = GetSessionAggregatesEndpointV1SessionsAggregatesGetBucket.DAY,
    severity_threshold: GetSessionAggregatesEndpointV1SessionsAggregatesGetSeverityThreshold,
    user_id: None | Unset | UUID = UNSET,
) -> Response[HTTPValidationError | SessionAggregatesResponse]:
    """Get Session Aggregates Endpoint

     Return organization-wide aggregate session metrics, optionally filtered by owner.

    Requires ``sessions:aggregates:read:any`` through a role or credential grant,
    including when filtering to the caller's own ``user_id``. Otherwise returns HTTP 403.

    Args:
        start_date (datetime.datetime | None | Unset):
        end_date (datetime.datetime | None | Unset):
        bucket (GetSessionAggregatesEndpointV1SessionsAggregatesGetBucket | Unset):  Default:
            GetSessionAggregatesEndpointV1SessionsAggregatesGetBucket.DAY.
        severity_threshold (GetSessionAggregatesEndpointV1SessionsAggregatesGetSeverityThreshold):
        user_id (None | Unset | UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | SessionAggregatesResponse]
    """

    kwargs = _get_kwargs(
        start_date=start_date,
        end_date=end_date,
        bucket=bucket,
        severity_threshold=severity_threshold,
        user_id=user_id,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient | Client,
    start_date: datetime.datetime | None | Unset = UNSET,
    end_date: datetime.datetime | None | Unset = UNSET,
    bucket: GetSessionAggregatesEndpointV1SessionsAggregatesGetBucket
    | Unset = GetSessionAggregatesEndpointV1SessionsAggregatesGetBucket.DAY,
    severity_threshold: GetSessionAggregatesEndpointV1SessionsAggregatesGetSeverityThreshold,
    user_id: None | Unset | UUID = UNSET,
) -> HTTPValidationError | SessionAggregatesResponse | None:
    """Get Session Aggregates Endpoint

     Return organization-wide aggregate session metrics, optionally filtered by owner.

    Requires ``sessions:aggregates:read:any`` through a role or credential grant,
    including when filtering to the caller's own ``user_id``. Otherwise returns HTTP 403.

    Args:
        start_date (datetime.datetime | None | Unset):
        end_date (datetime.datetime | None | Unset):
        bucket (GetSessionAggregatesEndpointV1SessionsAggregatesGetBucket | Unset):  Default:
            GetSessionAggregatesEndpointV1SessionsAggregatesGetBucket.DAY.
        severity_threshold (GetSessionAggregatesEndpointV1SessionsAggregatesGetSeverityThreshold):
        user_id (None | Unset | UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | SessionAggregatesResponse
    """

    return (
        await asyncio_detailed(
            client=client,
            start_date=start_date,
            end_date=end_date,
            bucket=bucket,
            severity_threshold=severity_threshold,
            user_id=user_id,
        )
    ).parsed
