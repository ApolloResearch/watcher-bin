from __future__ import annotations

from collections.abc import Mapping
from typing import (
    TYPE_CHECKING,
    Any,
    Literal,
    Self,
    TypeVar,
    cast,
)

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.content_citation import ContentCitation
    from ..models.document_citation import DocumentCitation
    from ..models.url_citation import UrlCitation


T = TypeVar("T", bound="ContentText")


@_attrs_define
class ContentText:
    """Text content.

    Attributes:
        text (str):
        internal (Any | None | Unset):
        type_ (Literal['text'] | Unset):  Default: 'text'.
        refusal (bool | None | Unset):
        citations (list[ContentCitation | DocumentCitation | UrlCitation] | None | Unset):
        cache_breakpoint (bool | None | Unset):
    """

    text: str
    internal: Any | None | Unset = UNSET
    type_: Literal["text"] | Unset = "text"
    refusal: bool | None | Unset = UNSET
    citations: list[ContentCitation | DocumentCitation | UrlCitation] | None | Unset = (
        UNSET
    )
    cache_breakpoint: bool | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.content_citation import ContentCitation
        from ..models.document_citation import DocumentCitation

        text = self.text

        internal: Any | None | Unset
        if isinstance(self.internal, Unset):
            internal = UNSET
        else:
            internal = self.internal

        type_ = self.type_

        refusal: bool | None | Unset
        if isinstance(self.refusal, Unset):
            refusal = UNSET
        else:
            refusal = self.refusal

        citations: list[dict[str, Any]] | None | Unset
        if isinstance(self.citations, Unset):
            citations = UNSET
        elif isinstance(self.citations, list):
            citations = []
            for citations_type_0_item_data in self.citations:
                citations_type_0_item: dict[str, Any]
                if isinstance(
                    citations_type_0_item_data, ContentCitation
                ) or isinstance(citations_type_0_item_data, DocumentCitation):
                    citations_type_0_item = citations_type_0_item_data.to_dict()
                else:
                    citations_type_0_item = citations_type_0_item_data.to_dict()

                citations.append(citations_type_0_item)

        else:
            citations = self.citations

        cache_breakpoint: bool | None | Unset
        if isinstance(self.cache_breakpoint, Unset):
            cache_breakpoint = UNSET
        else:
            cache_breakpoint = self.cache_breakpoint

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "text": text,
            }
        )
        if internal is not UNSET:
            field_dict["internal"] = internal
        if type_ is not UNSET:
            field_dict["type"] = type_
        if refusal is not UNSET:
            field_dict["refusal"] = refusal
        if citations is not UNSET:
            field_dict["citations"] = citations
        if cache_breakpoint is not UNSET:
            field_dict["cache_breakpoint"] = cache_breakpoint

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        from ..models.content_citation import ContentCitation
        from ..models.document_citation import DocumentCitation
        from ..models.url_citation import UrlCitation

        d = dict(src_dict)
        text = d.pop("text")

        def _parse_internal(data: object) -> Any | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(Any | None | Unset, data)

        internal = _parse_internal(d.pop("internal", UNSET))

        type_ = cast(Literal["text"] | Unset, d.pop("type", UNSET))
        if type_ != "text" and not isinstance(type_, Unset):
            raise ValueError(f"type must match const 'text', got '{type_}'")

        def _parse_refusal(data: object) -> bool | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(bool | None | Unset, data)

        refusal = _parse_refusal(d.pop("refusal", UNSET))

        def _parse_citations(
            data: object,
        ) -> list[ContentCitation | DocumentCitation | UrlCitation] | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                citations_type_0 = []
                _citations_type_0 = data
                for citations_type_0_item_data in _citations_type_0:

                    def _parse_citations_type_0_item(
                        data: object,
                    ) -> ContentCitation | DocumentCitation | UrlCitation:
                        try:
                            if not isinstance(data, dict):
                                raise TypeError()
                            citations_type_0_item_type_0 = ContentCitation.from_dict(
                                data
                            )

                            return citations_type_0_item_type_0
                        except (TypeError, ValueError, AttributeError, KeyError):
                            pass
                        try:
                            if not isinstance(data, dict):
                                raise TypeError()
                            citations_type_0_item_type_1 = DocumentCitation.from_dict(
                                data
                            )

                            return citations_type_0_item_type_1
                        except (TypeError, ValueError, AttributeError, KeyError):
                            pass
                        if not isinstance(data, dict):
                            raise TypeError()
                        citations_type_0_item_type_2 = UrlCitation.from_dict(data)

                        return citations_type_0_item_type_2

                    citations_type_0_item = _parse_citations_type_0_item(
                        citations_type_0_item_data
                    )

                    citations_type_0.append(citations_type_0_item)

                return citations_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(
                list[ContentCitation | DocumentCitation | UrlCitation] | None | Unset,
                data,
            )

        citations = _parse_citations(d.pop("citations", UNSET))

        def _parse_cache_breakpoint(data: object) -> bool | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(bool | None | Unset, data)

        cache_breakpoint = _parse_cache_breakpoint(d.pop("cache_breakpoint", UNSET))

        content_text = cls(
            text=text,
            internal=internal,
            type_=type_,
            refusal=refusal,
            citations=citations,
            cache_breakpoint=cache_breakpoint,
        )

        content_text.additional_properties = d
        return content_text

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
