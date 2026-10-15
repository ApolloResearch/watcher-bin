from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from typing_extensions import Self

from ..types import UNSET, Unset

T = TypeVar("T", bound="GradingUsageBucket")


@_attrs_define
class GradingUsageBucket:
    """One time bucket of the grading-usage aggregation.

    Request counts split by pipeline: ``trailing_requests`` are turn-review
    grades, ``triage_requests``/``gateway_requests`` are the two live
    pre-tool grading stages. ``cost`` is the estimated USD spend for the
    bucket (excluding unpriced models). Cost and token fields are null when the deployment does not expose raw token
    details (see ``GradingUsageResponse.token_details_enabled``); otherwise
    they are totals across the bucket. Cache token fields follow the naming of
    ``GradeUsage``: cache_write is tokens written to the provider prompt
    cache, cache_read is tokens served from it.

        Attributes:
            date (datetime.date):
            trailing_requests (int):
            triage_requests (int):
            gateway_requests (int):
            cost (float | None | Unset):
            input_tokens (int | None | Unset):
            output_tokens (int | None | Unset):
            reasoning_tokens (int | None | Unset):
            input_tokens_cache_read (int | None | Unset):
            input_tokens_cache_write (int | None | Unset):
    """

    date: datetime.date
    trailing_requests: int
    triage_requests: int
    gateway_requests: int
    cost: float | None | Unset = UNSET
    input_tokens: int | None | Unset = UNSET
    output_tokens: int | None | Unset = UNSET
    reasoning_tokens: int | None | Unset = UNSET
    input_tokens_cache_read: int | None | Unset = UNSET
    input_tokens_cache_write: int | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        date = self.date.isoformat()

        trailing_requests = self.trailing_requests

        triage_requests = self.triage_requests

        gateway_requests = self.gateway_requests

        cost: float | None | Unset
        if isinstance(self.cost, Unset):
            cost = UNSET
        else:
            cost = self.cost

        input_tokens: int | None | Unset
        if isinstance(self.input_tokens, Unset):
            input_tokens = UNSET
        else:
            input_tokens = self.input_tokens

        output_tokens: int | None | Unset
        if isinstance(self.output_tokens, Unset):
            output_tokens = UNSET
        else:
            output_tokens = self.output_tokens

        reasoning_tokens: int | None | Unset
        if isinstance(self.reasoning_tokens, Unset):
            reasoning_tokens = UNSET
        else:
            reasoning_tokens = self.reasoning_tokens

        input_tokens_cache_read: int | None | Unset
        if isinstance(self.input_tokens_cache_read, Unset):
            input_tokens_cache_read = UNSET
        else:
            input_tokens_cache_read = self.input_tokens_cache_read

        input_tokens_cache_write: int | None | Unset
        if isinstance(self.input_tokens_cache_write, Unset):
            input_tokens_cache_write = UNSET
        else:
            input_tokens_cache_write = self.input_tokens_cache_write

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "date": date,
                "trailing_requests": trailing_requests,
                "triage_requests": triage_requests,
                "gateway_requests": gateway_requests,
            }
        )
        if cost is not UNSET:
            field_dict["cost"] = cost
        if input_tokens is not UNSET:
            field_dict["input_tokens"] = input_tokens
        if output_tokens is not UNSET:
            field_dict["output_tokens"] = output_tokens
        if reasoning_tokens is not UNSET:
            field_dict["reasoning_tokens"] = reasoning_tokens
        if input_tokens_cache_read is not UNSET:
            field_dict["input_tokens_cache_read"] = input_tokens_cache_read
        if input_tokens_cache_write is not UNSET:
            field_dict["input_tokens_cache_write"] = input_tokens_cache_write

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        d = dict(src_dict)
        date = datetime.date.fromisoformat(d.pop("date"))

        trailing_requests = d.pop("trailing_requests")

        triage_requests = d.pop("triage_requests")

        gateway_requests = d.pop("gateway_requests")

        def _parse_cost(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        cost = _parse_cost(d.pop("cost", UNSET))

        def _parse_input_tokens(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        input_tokens = _parse_input_tokens(d.pop("input_tokens", UNSET))

        def _parse_output_tokens(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        output_tokens = _parse_output_tokens(d.pop("output_tokens", UNSET))

        def _parse_reasoning_tokens(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        reasoning_tokens = _parse_reasoning_tokens(d.pop("reasoning_tokens", UNSET))

        def _parse_input_tokens_cache_read(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        input_tokens_cache_read = _parse_input_tokens_cache_read(
            d.pop("input_tokens_cache_read", UNSET)
        )

        def _parse_input_tokens_cache_write(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        input_tokens_cache_write = _parse_input_tokens_cache_write(
            d.pop("input_tokens_cache_write", UNSET)
        )

        grading_usage_bucket = cls(
            date=date,
            trailing_requests=trailing_requests,
            triage_requests=triage_requests,
            gateway_requests=gateway_requests,
            cost=cost,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            reasoning_tokens=reasoning_tokens,
            input_tokens_cache_read=input_tokens_cache_read,
            input_tokens_cache_write=input_tokens_cache_write,
        )

        grading_usage_bucket.additional_properties = d
        return grading_usage_bucket

    @property
    def additional_keys(self) -> list[str]:
        return list(self.additional_properties.keys())

    def __getitem__(self, key: str) -> Any:
        return self.additional_properties[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self.additional_properties[key] = value

    def __delitem__(self, key: str) -> None:
        del self.additional_properties[key]

    def __contains__(self, key: str) -> bool:
        return key in self.additional_properties
