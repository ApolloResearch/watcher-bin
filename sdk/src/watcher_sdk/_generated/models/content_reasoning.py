from __future__ import annotations

from collections.abc import Mapping
from typing import (
    Any,
    Literal,
    TypeVar,
    cast,
)

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from typing_extensions import Self

from ..types import UNSET, Unset

T = TypeVar("T", bound="ContentReasoning")


@_attrs_define
class ContentReasoning:
    """Reasoning content.

    See the specification for [thinking blocks](https://docs.anthropic.com/en/docs/build-with-claude/extended-
    thinking#understanding-thinking-blocks) for Claude models.

        Attributes:
            reasoning (str):
            internal (Any | None | Unset):
            type_ (Literal['reasoning'] | Unset):  Default: 'reasoning'.
            summary (None | str | Unset):
            signature (None | str | Unset):
            redacted (bool | Unset):  Default: False.
    """

    reasoning: str
    internal: Any | None | Unset = UNSET
    type_: Literal["reasoning"] | Unset = "reasoning"
    summary: None | str | Unset = UNSET
    signature: None | str | Unset = UNSET
    redacted: bool | Unset = False
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        reasoning = self.reasoning

        internal: Any | None | Unset
        if isinstance(self.internal, Unset):
            internal = UNSET
        else:
            internal = self.internal

        type_ = self.type_

        summary: None | str | Unset
        if isinstance(self.summary, Unset):
            summary = UNSET
        else:
            summary = self.summary

        signature: None | str | Unset
        if isinstance(self.signature, Unset):
            signature = UNSET
        else:
            signature = self.signature

        redacted = self.redacted

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "reasoning": reasoning,
            }
        )
        if internal is not UNSET:
            field_dict["internal"] = internal
        if type_ is not UNSET:
            field_dict["type"] = type_
        if summary is not UNSET:
            field_dict["summary"] = summary
        if signature is not UNSET:
            field_dict["signature"] = signature
        if redacted is not UNSET:
            field_dict["redacted"] = redacted

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        d = dict(src_dict)
        reasoning = d.pop("reasoning")

        def _parse_internal(data: object) -> Any | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(Any | None | Unset, data)

        internal = _parse_internal(d.pop("internal", UNSET))

        type_ = cast(Literal["reasoning"] | Unset, d.pop("type", UNSET))
        if type_ != "reasoning" and not isinstance(type_, Unset):
            raise ValueError(f"type must match const 'reasoning', got '{type_}'")

        def _parse_summary(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        summary = _parse_summary(d.pop("summary", UNSET))

        def _parse_signature(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        signature = _parse_signature(d.pop("signature", UNSET))

        redacted = d.pop("redacted", UNSET)

        content_reasoning = cls(
            reasoning=reasoning,
            internal=internal,
            type_=type_,
            summary=summary,
            signature=signature,
            redacted=redacted,
        )

        content_reasoning.additional_properties = d
        return content_reasoning

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
