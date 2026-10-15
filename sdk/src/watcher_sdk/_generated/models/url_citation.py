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
    from ..models.url_citation_internal_type_0 import UrlCitationInternalType0


T = TypeVar("T", bound="UrlCitation")


@_attrs_define
class UrlCitation:
    """A citation that refers to a URL.

    Attributes:
        url (str):
        cited_text (list[int] | None | str | Unset):
        title (None | str | Unset):
        internal (None | Unset | UrlCitationInternalType0):
        type_ (Literal['url'] | Unset):  Default: 'url'.
    """

    url: str
    cited_text: list[int] | None | str | Unset = UNSET
    title: None | str | Unset = UNSET
    internal: None | Unset | UrlCitationInternalType0 = UNSET
    type_: Literal["url"] | Unset = "url"
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.url_citation_internal_type_0 import (
            UrlCitationInternalType0,
        )

        url = self.url

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
        elif isinstance(self.internal, UrlCitationInternalType0):
            internal = self.internal.to_dict()
        else:
            internal = self.internal

        type_ = self.type_

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "url": url,
            }
        )
        if cited_text is not UNSET:
            field_dict["cited_text"] = cited_text
        if title is not UNSET:
            field_dict["title"] = title
        if internal is not UNSET:
            field_dict["internal"] = internal
        if type_ is not UNSET:
            field_dict["type"] = type_

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        from ..models.url_citation_internal_type_0 import (
            UrlCitationInternalType0,
        )

        d = dict(src_dict)
        url = d.pop("url")

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

        def _parse_internal(data: object) -> None | Unset | UrlCitationInternalType0:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                internal_type_0 = UrlCitationInternalType0.from_dict(data)

                return internal_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | Unset | UrlCitationInternalType0, data)

        internal = _parse_internal(d.pop("internal", UNSET))

        type_ = cast(Literal["url"] | Unset, d.pop("type", UNSET))
        if type_ != "url" and not isinstance(type_, Unset):
            raise ValueError(f"type must match const 'url', got '{type_}'")

        url_citation = cls(
            url=url,
            cited_text=cited_text,
            title=title,
            internal=internal,
            type_=type_,
        )

        url_citation.additional_properties = d
        return url_citation

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
