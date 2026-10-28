from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Self, TypeVar

from attrs import define as _attrs_define

from ..types import UNSET, Unset

T = TypeVar("T", bound="ModelTokenBudget")


@_attrs_define
class ModelTokenBudget:
    """Token-sizing facts a client needs to fit input to one model family.

    ``max_input_tokens`` is the model's whole context window and
    ``max_output_tokens`` its output cap — a client derives its input budget by
    subtraction. The tiktoken fields describe how to count: the encoding the
    client should tokenize with, and a scaling factor correcting for tokenizers
    tiktoken cannot represent.

        Attributes:
            max_input_tokens (int):
            max_output_tokens (int):
            tiktoken_encoding (str | Unset):  Default: 'cl100k_base'.
            tiktoken_scaling_factor (float | Unset):  Default: 1.0.
    """

    max_input_tokens: int
    max_output_tokens: int
    tiktoken_encoding: str | Unset = "cl100k_base"
    tiktoken_scaling_factor: float | Unset = 1.0

    def to_dict(self) -> dict[str, Any]:
        max_input_tokens = self.max_input_tokens

        max_output_tokens = self.max_output_tokens

        tiktoken_encoding = self.tiktoken_encoding

        tiktoken_scaling_factor = self.tiktoken_scaling_factor

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "max_input_tokens": max_input_tokens,
                "max_output_tokens": max_output_tokens,
            }
        )
        if tiktoken_encoding is not UNSET:
            field_dict["tiktoken_encoding"] = tiktoken_encoding
        if tiktoken_scaling_factor is not UNSET:
            field_dict["tiktoken_scaling_factor"] = tiktoken_scaling_factor

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        d = dict(src_dict)
        max_input_tokens = d.pop("max_input_tokens")

        max_output_tokens = d.pop("max_output_tokens")

        tiktoken_encoding = d.pop("tiktoken_encoding", UNSET)

        tiktoken_scaling_factor = d.pop("tiktoken_scaling_factor", UNSET)

        model_token_budget = cls(
            max_input_tokens=max_input_tokens,
            max_output_tokens=max_output_tokens,
            tiktoken_encoding=tiktoken_encoding,
            tiktoken_scaling_factor=tiktoken_scaling_factor,
        )

        return model_token_budget
