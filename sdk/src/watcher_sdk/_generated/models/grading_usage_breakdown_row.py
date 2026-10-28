from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Self, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="GradingUsageBreakdownRow")


@_attrs_define
class GradingUsageBreakdownRow:
    """Usage totals for one breakdown value (a user, model, or grader).

    ``key`` is the stable identifier (user id, model name, or grader id) and
    ``label`` the display name (email, model name, or grader name); both are
    null for usage that cannot be attributed to the dimension (e.g. live
    grades whose decision never linked back to a session). Token-field
    semantics match ``GradingUsageBucket``.

        Attributes:
            trailing_requests (int):
            triage_requests (int):
            gateway_requests (int):
            key (None | str | Unset):
            label (None | str | Unset):
            cost (float | None | Unset):
            input_tokens (int | None | Unset):
            output_tokens (int | None | Unset):
            reasoning_tokens (int | None | Unset):
            input_tokens_cache_read (int | None | Unset):
            input_tokens_cache_write (int | None | Unset):
    """

    trailing_requests: int
    triage_requests: int
    gateway_requests: int
    key: None | str | Unset = UNSET
    label: None | str | Unset = UNSET
    cost: float | None | Unset = UNSET
    input_tokens: int | None | Unset = UNSET
    output_tokens: int | None | Unset = UNSET
    reasoning_tokens: int | None | Unset = UNSET
    input_tokens_cache_read: int | None | Unset = UNSET
    input_tokens_cache_write: int | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        trailing_requests = self.trailing_requests

        triage_requests = self.triage_requests

        gateway_requests = self.gateway_requests

        key: None | str | Unset
        if isinstance(self.key, Unset):
            key = UNSET
        else:
            key = self.key

        label: None | str | Unset
        if isinstance(self.label, Unset):
            label = UNSET
        else:
            label = self.label

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
                "trailing_requests": trailing_requests,
                "triage_requests": triage_requests,
                "gateway_requests": gateway_requests,
            }
        )
        if key is not UNSET:
            field_dict["key"] = key
        if label is not UNSET:
            field_dict["label"] = label
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
        trailing_requests = d.pop("trailing_requests")

        triage_requests = d.pop("triage_requests")

        gateway_requests = d.pop("gateway_requests")

        def _parse_key(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        key = _parse_key(d.pop("key", UNSET))

        def _parse_label(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        label = _parse_label(d.pop("label", UNSET))

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

        grading_usage_breakdown_row = cls(
            trailing_requests=trailing_requests,
            triage_requests=triage_requests,
            gateway_requests=gateway_requests,
            key=key,
            label=label,
            cost=cost,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            reasoning_tokens=reasoning_tokens,
            input_tokens_cache_read=input_tokens_cache_read,
            input_tokens_cache_write=input_tokens_cache_write,
        )

        grading_usage_breakdown_row.additional_properties = d
        return grading_usage_breakdown_row

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
