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

T = TypeVar("T", bound="ContentDocument")


@_attrs_define
class ContentDocument:
    """Document content (e.g. a PDF).

    Attributes:
        document (str):
        internal (Any | None | Unset):
        type_ (Literal['document'] | Unset):  Default: 'document'.
        filename (str | Unset):
        mime_type (str | Unset):
        citations (bool | Unset):  Default: False.
    """

    document: str
    internal: Any | None | Unset = UNSET
    type_: Literal["document"] | Unset = "document"
    filename: str | Unset = UNSET
    mime_type: str | Unset = UNSET
    citations: bool | Unset = False
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        document = self.document

        internal: Any | None | Unset
        if isinstance(self.internal, Unset):
            internal = UNSET
        else:
            internal = self.internal

        type_ = self.type_

        filename = self.filename

        mime_type = self.mime_type

        citations = self.citations

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "document": document,
            }
        )
        if internal is not UNSET:
            field_dict["internal"] = internal
        if type_ is not UNSET:
            field_dict["type"] = type_
        if filename is not UNSET:
            field_dict["filename"] = filename
        if mime_type is not UNSET:
            field_dict["mime_type"] = mime_type
        if citations is not UNSET:
            field_dict["citations"] = citations

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        d = dict(src_dict)
        document = d.pop("document")

        def _parse_internal(data: object) -> Any | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(Any | None | Unset, data)

        internal = _parse_internal(d.pop("internal", UNSET))

        type_ = cast(Literal["document"] | Unset, d.pop("type", UNSET))
        if type_ != "document" and not isinstance(type_, Unset):
            raise ValueError(f"type must match const 'document', got '{type_}'")

        filename = d.pop("filename", UNSET)

        mime_type = d.pop("mime_type", UNSET)

        citations = d.pop("citations", UNSET)

        content_document = cls(
            document=document,
            internal=internal,
            type_=type_,
            filename=filename,
            mime_type=mime_type,
            citations=citations,
        )

        content_document.additional_properties = d
        return content_document

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
