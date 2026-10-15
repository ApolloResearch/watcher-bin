from __future__ import annotations

from collections.abc import Mapping
from typing import (
    TYPE_CHECKING,
    Any,
    Literal,
    TypeVar,
    cast,
)

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from typing_extensions import Self

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.document_citation_internal_type_0 import DocumentCitationInternalType0
    from ..models.document_range import DocumentRange


T = TypeVar("T", bound="DocumentCitation")


@_attrs_define
class DocumentCitation:
    """A citation that refers to a page range in a document.

    Attributes:
        cited_text (list[int] | None | str | Unset):
        title (None | str | Unset):
        internal (DocumentCitationInternalType0 | None | Unset):
        type_ (Literal['document'] | Unset):  Default: 'document'.
        range_ (DocumentRange | None | Unset):
    """

    cited_text: list[int] | None | str | Unset = UNSET
    title: None | str | Unset = UNSET
    internal: DocumentCitationInternalType0 | None | Unset = UNSET
    type_: Literal["document"] | Unset = "document"
    range_: DocumentRange | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.document_citation_internal_type_0 import (
            DocumentCitationInternalType0,
        )
        from ..models.document_range import DocumentRange

        cited_text: list[int] | None | str | Unset
        if isinstance(self.cited_text, Unset):
            cited_text = UNSET
        elif isinstance(self.cited_text, list):
            cited_text = self.cited_text

        else:
            cited_text = self.cited_text

        title: None | str | Unset
        if isinstance(self.title, Unset):
            title = UNSET
        else:
            title = self.title

        internal: dict[str, Any] | None | Unset
        if isinstance(self.internal, Unset):
            internal = UNSET
        elif isinstance(self.internal, DocumentCitationInternalType0):
            internal = self.internal.to_dict()
        else:
            internal = self.internal

        type_ = self.type_

        range_: dict[str, Any] | None | Unset
        if isinstance(self.range_, Unset):
            range_ = UNSET
        elif isinstance(self.range_, DocumentRange):
            range_ = self.range_.to_dict()
        else:
            range_ = self.range_

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if cited_text is not UNSET:
            field_dict["cited_text"] = cited_text
        if title is not UNSET:
            field_dict["title"] = title
        if internal is not UNSET:
            field_dict["internal"] = internal
        if type_ is not UNSET:
            field_dict["type"] = type_
        if range_ is not UNSET:
            field_dict["range"] = range_

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        from ..models.document_citation_internal_type_0 import (
            DocumentCitationInternalType0,
        )
        from ..models.document_range import DocumentRange

        d = dict(src_dict)

        def _parse_cited_text(data: object) -> list[int] | None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                cited_text_type_1 = cast(list[int], data)

                return cited_text_type_1
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(list[int] | None | str | Unset, data)

        cited_text = _parse_cited_text(d.pop("cited_text", UNSET))

        def _parse_title(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        title = _parse_title(d.pop("title", UNSET))

        def _parse_internal(
            data: object,
        ) -> DocumentCitationInternalType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                internal_type_0 = DocumentCitationInternalType0.from_dict(data)

                return internal_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(DocumentCitationInternalType0 | None | Unset, data)

        internal = _parse_internal(d.pop("internal", UNSET))

        type_ = cast(Literal["document"] | Unset, d.pop("type", UNSET))
        if type_ != "document" and not isinstance(type_, Unset):
            raise ValueError(f"type must match const 'document', got '{type_}'")

        def _parse_range_(data: object) -> DocumentRange | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                range_type_0 = DocumentRange.from_dict(data)

                return range_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(DocumentRange | None | Unset, data)

        range_ = _parse_range_(d.pop("range", UNSET))

        document_citation = cls(
            cited_text=cited_text,
            title=title,
            internal=internal,
            type_=type_,
            range_=range_,
        )

        document_citation.additional_properties = d
        return document_citation

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
