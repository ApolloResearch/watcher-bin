import datetime
from http import HTTPStatus
from typing import Any
from uuid import UUID

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.get_grading_usage_endpoint_v1_usage_grading_get_bucket import (
    GetGradingUsageEndpointV1UsageGradingGetBucket,
)
from ...models.get_grading_usage_endpoint_v1_usage_grading_get_kind import (
    GetGradingUsageEndpointV1UsageGradingGetKind,
)
from ...models.grading_usage_response import GradingUsageResponse
from ...models.http_validation_error import HTTPValidationError
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    start_date: datetime.datetime | None | Unset = UNSET,
    end_date: datetime.datetime | None | Unset = UNSET,
    bucket: GetGradingUsageEndpointV1UsageGradingGetBucket
    | Unset = GetGradingUsageEndpointV1UsageGradingGetBucket.DAY,
    kind: GetGradingUsageEndpointV1UsageGradingGetKind
    | Unset = GetGradingUsageEndpointV1UsageGradingGetKind.ALL,
    user_id: None | Unset | UUID = UNSET,
    model: None | str | Unset = UNSET,
    grader_id: None | Unset | UUID = UNSET,
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

    json_kind: str | Unset = UNSET
    if not isinstance(kind, Unset):
        json_kind = kind.value

    params["kind"] = json_kind

    json_user_id: None | str | Unset
    if isinstance(user_id, Unset):
        json_user_id = UNSET
    elif isinstance(user_id, UUID):
        json_user_id = str(user_id)
    else:
        json_user_id = user_id
    params["user_id"] = json_user_id

    json_model: None | str | Unset
    if isinstance(model, Unset):
        json_model = UNSET
    else:
        json_model = model
    params["model"] = json_model

    json_grader_id: None | str | Unset
    if isinstance(grader_id, Unset):
        json_grader_id = UNSET
    elif isinstance(grader_id, UUID):
        json_grader_id = str(grader_id)
    else:
        json_grader_id = grader_id
    params["grader_id"] = json_grader_id

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/v1/usage/grading",
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> GradingUsageResponse | HTTPValidationError | None:
    if response.status_code == 200:
        response_200 = GradingUsageResponse.from_dict(response.json())

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
) -> Response[GradingUsageResponse | HTTPValidationError]:
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
    bucket: GetGradingUsageEndpointV1UsageGradingGetBucket
    | Unset = GetGradingUsageEndpointV1UsageGradingGetBucket.DAY,
    kind: GetGradingUsageEndpointV1UsageGradingGetKind
    | Unset = GetGradingUsageEndpointV1UsageGradingGetKind.ALL,
    user_id: None | Unset | UUID = UNSET,
    model: None | str | Unset = UNSET,
    grader_id: None | Unset | UUID = UNSET,
) -> Response[GradingUsageResponse | HTTPValidationError]:
    """Get Grading Usage Endpoint

     Return grading usage aggregates: a by-date series plus per-user/model/grader window totals.

    The date window is capped at 180 days: wider explicit ranges are rejected
    with 422, and an omitted ``start_date`` defaults to 180 days before
    ``end_date`` (or now).

    Args:
        start_date (datetime.datetime | None | Unset): Window start; defaults to 180 days before
            end_date.
        end_date (datetime.datetime | None | Unset): Window end; defaults to now.
        bucket (GetGradingUsageEndpointV1UsageGradingGetBucket | Unset):  Default:
            GetGradingUsageEndpointV1UsageGradingGetBucket.DAY.
        kind (GetGradingUsageEndpointV1UsageGradingGetKind | Unset):  Default:
            GetGradingUsageEndpointV1UsageGradingGetKind.ALL.
        user_id (None | Unset | UUID):
        model (None | str | Unset):
        grader_id (None | Unset | UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[GradingUsageResponse | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        start_date=start_date,
        end_date=end_date,
        bucket=bucket,
        kind=kind,
        user_id=user_id,
        model=model,
        grader_id=grader_id,
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
    bucket: GetGradingUsageEndpointV1UsageGradingGetBucket
    | Unset = GetGradingUsageEndpointV1UsageGradingGetBucket.DAY,
    kind: GetGradingUsageEndpointV1UsageGradingGetKind
    | Unset = GetGradingUsageEndpointV1UsageGradingGetKind.ALL,
    user_id: None | Unset | UUID = UNSET,
    model: None | str | Unset = UNSET,
    grader_id: None | Unset | UUID = UNSET,
) -> GradingUsageResponse | HTTPValidationError | None:
    """Get Grading Usage Endpoint

     Return grading usage aggregates: a by-date series plus per-user/model/grader window totals.

    The date window is capped at 180 days: wider explicit ranges are rejected
    with 422, and an omitted ``start_date`` defaults to 180 days before
    ``end_date`` (or now).

    Args:
        start_date (datetime.datetime | None | Unset): Window start; defaults to 180 days before
            end_date.
        end_date (datetime.datetime | None | Unset): Window end; defaults to now.
        bucket (GetGradingUsageEndpointV1UsageGradingGetBucket | Unset):  Default:
            GetGradingUsageEndpointV1UsageGradingGetBucket.DAY.
        kind (GetGradingUsageEndpointV1UsageGradingGetKind | Unset):  Default:
            GetGradingUsageEndpointV1UsageGradingGetKind.ALL.
        user_id (None | Unset | UUID):
        model (None | str | Unset):
        grader_id (None | Unset | UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        GradingUsageResponse | HTTPValidationError
    """

    return sync_detailed(
        client=client,
        start_date=start_date,
        end_date=end_date,
        bucket=bucket,
        kind=kind,
        user_id=user_id,
        model=model,
        grader_id=grader_id,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient | Client,
    start_date: datetime.datetime | None | Unset = UNSET,
    end_date: datetime.datetime | None | Unset = UNSET,
    bucket: GetGradingUsageEndpointV1UsageGradingGetBucket
    | Unset = GetGradingUsageEndpointV1UsageGradingGetBucket.DAY,
    kind: GetGradingUsageEndpointV1UsageGradingGetKind
    | Unset = GetGradingUsageEndpointV1UsageGradingGetKind.ALL,
    user_id: None | Unset | UUID = UNSET,
    model: None | str | Unset = UNSET,
    grader_id: None | Unset | UUID = UNSET,
) -> Response[GradingUsageResponse | HTTPValidationError]:
    """Get Grading Usage Endpoint

     Return grading usage aggregates: a by-date series plus per-user/model/grader window totals.

    The date window is capped at 180 days: wider explicit ranges are rejected
    with 422, and an omitted ``start_date`` defaults to 180 days before
    ``end_date`` (or now).

    Args:
        start_date (datetime.datetime | None | Unset): Window start; defaults to 180 days before
            end_date.
        end_date (datetime.datetime | None | Unset): Window end; defaults to now.
        bucket (GetGradingUsageEndpointV1UsageGradingGetBucket | Unset):  Default:
            GetGradingUsageEndpointV1UsageGradingGetBucket.DAY.
        kind (GetGradingUsageEndpointV1UsageGradingGetKind | Unset):  Default:
            GetGradingUsageEndpointV1UsageGradingGetKind.ALL.
        user_id (None | Unset | UUID):
        model (None | str | Unset):
        grader_id (None | Unset | UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[GradingUsageResponse | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        start_date=start_date,
        end_date=end_date,
        bucket=bucket,
        kind=kind,
        user_id=user_id,
        model=model,
        grader_id=grader_id,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient | Client,
    start_date: datetime.datetime | None | Unset = UNSET,
    end_date: datetime.datetime | None | Unset = UNSET,
    bucket: GetGradingUsageEndpointV1UsageGradingGetBucket
    | Unset = GetGradingUsageEndpointV1UsageGradingGetBucket.DAY,
    kind: GetGradingUsageEndpointV1UsageGradingGetKind
    | Unset = GetGradingUsageEndpointV1UsageGradingGetKind.ALL,
    user_id: None | Unset | UUID = UNSET,
    model: None | str | Unset = UNSET,
    grader_id: None | Unset | UUID = UNSET,
) -> GradingUsageResponse | HTTPValidationError | None:
    """Get Grading Usage Endpoint

     Return grading usage aggregates: a by-date series plus per-user/model/grader window totals.

    The date window is capped at 180 days: wider explicit ranges are rejected
    with 422, and an omitted ``start_date`` defaults to 180 days before
    ``end_date`` (or now).

    Args:
        start_date (datetime.datetime | None | Unset): Window start; defaults to 180 days before
            end_date.
        end_date (datetime.datetime | None | Unset): Window end; defaults to now.
        bucket (GetGradingUsageEndpointV1UsageGradingGetBucket | Unset):  Default:
            GetGradingUsageEndpointV1UsageGradingGetBucket.DAY.
        kind (GetGradingUsageEndpointV1UsageGradingGetKind | Unset):  Default:
            GetGradingUsageEndpointV1UsageGradingGetKind.ALL.
        user_id (None | Unset | UUID):
        model (None | str | Unset):
        grader_id (None | Unset | UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        GradingUsageResponse | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            client=client,
            start_date=start_date,
            end_date=end_date,
            bucket=bucket,
            kind=kind,
            user_id=user_id,
            model=model,
            grader_id=grader_id,
        )
    ).parsed
