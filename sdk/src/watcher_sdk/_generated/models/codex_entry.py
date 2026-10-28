from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Self, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.codex_payload import CodexPayload


T = TypeVar("T", bound="CodexEntry")


@_attrs_define
class CodexEntry:
    """One line from a Codex session rollout file. ``type`` says which payload fields are set.

    Attributes:
        type_ (str):
        timestamp (str):
        payload (CodexPayload | None | Unset):
        ordinal (int | None | Unset):
    """

    type_: str
    timestamp: str
    payload: CodexPayload | None | Unset = UNSET
    ordinal: int | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.codex_payload import CodexPayload

        type_ = self.type_

        timestamp = self.timestamp

        payload: dict[str, Any] | None | Unset
        if isinstance(self.payload, Unset):
            payload = UNSET
        elif isinstance(self.payload, CodexPayload):
            payload = self.payload.to_dict()
        else:
            payload = self.payload

        ordinal: int | None | Unset
        if isinstance(self.ordinal, Unset):
            ordinal = UNSET
        else:
            ordinal = self.ordinal

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "type": type_,
                "timestamp": timestamp,
            }
        )
        if payload is not UNSET:
            field_dict["payload"] = payload
        if ordinal is not UNSET:
            field_dict["ordinal"] = ordinal

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        from ..models.codex_payload import CodexPayload

        d = dict(src_dict)
        type_ = d.pop("type")

        timestamp = d.pop("timestamp")

        def _parse_payload(data: object) -> CodexPayload | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                payload_type_0 = CodexPayload.from_dict(data)

                return payload_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(CodexPayload | None | Unset, data)

        payload = _parse_payload(d.pop("payload", UNSET))

        def _parse_ordinal(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        ordinal = _parse_ordinal(d.pop("ordinal", UNSET))

        codex_entry = cls(
            type_=type_,
            timestamp=timestamp,
            payload=payload,
            ordinal=ordinal,
        )

        codex_entry.additional_properties = d
        return codex_entry

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
