from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Self, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.content_block import ContentBlock


T = TypeVar("T", bound="ClaudeCodeAttachment")


@_attrs_define
class ClaudeCodeAttachment:
    """Payload of an ``attachment``-type JSONL entry.

    Attachments carry out-of-band context injected into the conversation (hook
    output, task reminders, diagnostics, ...). Almost all of them are telemetry,
    with one exception that matters for ingestion: ``type == "queued_command"``
    records the delivery of a message the human typed while the agent was
    mid-turn. Queued messages are written to the JSONL *only* as this attachment
    (plus a ``queue-operation`` enqueue record) — there is no corresponding
    ``user`` entry — so the human's words live exclusively in ``prompt``.

    ``prompt`` is a plain string for text-only messages, or a list of content
    blocks when the queued message included images. Empirically no other
    attachment type carries a ``prompt``.

        Attributes:
            type_ (str):
            prompt (list[ContentBlock] | None | str | Unset):
    """

    type_: str
    prompt: list[ContentBlock] | None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        type_ = self.type_

        prompt: list[dict[str, Any]] | None | str | Unset
        if isinstance(self.prompt, Unset):
            prompt = UNSET
        elif isinstance(self.prompt, list):
            prompt = []
            for prompt_type_1_item_data in self.prompt:
                prompt_type_1_item = prompt_type_1_item_data.to_dict()
                prompt.append(prompt_type_1_item)

        else:
            prompt = self.prompt

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "type": type_,
            }
        )
        if prompt is not UNSET:
            field_dict["prompt"] = prompt

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        from ..models.content_block import ContentBlock

        d = dict(src_dict)
        type_ = d.pop("type")

        def _parse_prompt(data: object) -> list[ContentBlock] | None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                prompt_type_1 = []
                _prompt_type_1 = data
                for prompt_type_1_item_data in _prompt_type_1:
                    prompt_type_1_item = ContentBlock.from_dict(prompt_type_1_item_data)

                    prompt_type_1.append(prompt_type_1_item)

                return prompt_type_1
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(list[ContentBlock] | None | str | Unset, data)

        prompt = _parse_prompt(d.pop("prompt", UNSET))

        claude_code_attachment = cls(
            type_=type_,
            prompt=prompt,
        )

        claude_code_attachment.additional_properties = d
        return claude_code_attachment

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
