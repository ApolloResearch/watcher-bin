from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.available_session_detail_response import AvailableSessionDetailResponse
from ...models.http_validation_error import HTTPValidationError
from ...models.scrubbed_session_detail_response import ScrubbedSessionDetailResponse
from ...types import Response


def _get_kwargs(
    session_id: str,
) -> dict[str, Any]:

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/v1/sessions/{session_id}".format(
            session_id=quote(str(session_id), safe=""),
        ),
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> (
    AvailableSessionDetailResponse
    | ScrubbedSessionDetailResponse
    | HTTPValidationError
    | None
):
    if response.status_code == 200:

        def _parse_response_200(
            data: object,
        ) -> AvailableSessionDetailResponse | ScrubbedSessionDetailResponse:
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                componentsschemas_session_detail_response_type_0 = (
                    ScrubbedSessionDetailResponse.from_dict(data)
                )

                return componentsschemas_session_detail_response_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            if not isinstance(data, dict):
                raise TypeError()
            componentsschemas_session_detail_response_type_1 = (
                AvailableSessionDetailResponse.from_dict(data)
            )

            return componentsschemas_session_detail_response_type_1

        response_200 = _parse_response_200(response.json())

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
) -> Response[
    AvailableSessionDetailResponse | ScrubbedSessionDetailResponse | HTTPValidationError
]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    session_id: str,
    *,
    client: AuthenticatedClient | Client,
) -> Response[
    AvailableSessionDetailResponse | ScrubbedSessionDetailResponse | HTTPValidationError
]:
    """Get Session Detail

     Get full session detail including trajectories and grades. 404 for sessions the caller can't read.

    Args:
        session_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[AvailableSessionDetailResponse | ScrubbedSessionDetailResponse | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        session_id=session_id,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    session_id: str,
    *,
    client: AuthenticatedClient | Client,
) -> (
    AvailableSessionDetailResponse
    | ScrubbedSessionDetailResponse
    | HTTPValidationError
    | None
):
    """Get Session Detail

     Get full session detail including trajectories and grades. 404 for sessions the caller can't read.

    Args:
        session_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        AvailableSessionDetailResponse | ScrubbedSessionDetailResponse | HTTPValidationError
    """

    return sync_detailed(
        session_id=session_id,
        client=client,
    ).parsed


async def asyncio_detailed(
    session_id: str,
    *,
    client: AuthenticatedClient | Client,
) -> Response[
    AvailableSessionDetailResponse | ScrubbedSessionDetailResponse | HTTPValidationError
]:
    """Get Session Detail

     Get full session detail including trajectories and grades. 404 for sessions the caller can't read.

    Args:
        session_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[AvailableSessionDetailResponse | ScrubbedSessionDetailResponse | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        session_id=session_id,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    session_id: str,
    *,
    client: AuthenticatedClient | Client,
) -> (
    AvailableSessionDetailResponse
    | ScrubbedSessionDetailResponse
    | HTTPValidationError
    | None
):
    """Get Session Detail

     Get full session detail including trajectories and grades. 404 for sessions the caller can't read.

    Args:
        session_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        AvailableSessionDetailResponse | ScrubbedSessionDetailResponse | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            session_id=session_id,
            client=client,
        )
    ).parsed
