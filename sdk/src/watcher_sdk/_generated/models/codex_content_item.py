from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.codex_content_item_type_type_0 import CodexContentItemTypeType0
from ..types import UNSET, Unset

T = TypeVar("T", bound="CodexContentItem")


@_attrs_define
class CodexContentItem:
    """One item inside a ``content`` or ``output`` array.

    The ``type`` annotation lists the values the parser handles. Unknown
    values still parse (they fall through the ``| str`` branch); handlers
    in ``product.lib.codex`` ignore items whose ``type`` they don't know.

        Attributes:
            type_ (CodexContentItemTypeType0 | None | str | Unset):
            text (None | str | Unset):
            image_url (None | str | Unset):
            detail (None | str | Unset):
    """

    type_: CodexContentItemTypeType0 | None | str | Unset = UNSET
    text: None | str | Unset = UNSET
    image_url: None | str | Unset = UNSET
    detail: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        type_: None | str | Unset
        if isinstance(self.type_, Unset):
            type_ = UNSET
        elif isinstance(self.type_, CodexContentItemTypeType0):
            type_ = self.type_.value
        else:
            type_ = self.type_

        text: None | str | Unset
        if isinstance(self.text, Unset):
            text = UNSET
        else:
            text = self.text

        image_url: None | str | Unset
        if isinstance(self.image_url, Unset):
            image_url = UNSET
        else:
            image_url = self.image_url

        detail: None | str | Unset
        if isinstance(self.detail, Unset):
            detail = UNSET
        else:
            detail = self.detail

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if type_ is not UNSET:
            field_dict["type"] = type_
        if text is not UNSET:
            field_dict["text"] = text
        if image_url is not UNSET:
            field_dict["image_url"] = image_url
        if detail is not UNSET:
            field_dict["detail"] = detail

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)

        def _parse_type_(
            data: object,
        ) -> CodexContentItemTypeType0 | None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                type_type_0 = CodexContentItemTypeType0(data)

                return type_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(CodexContentItemTypeType0 | None | str | Unset, data)

        type_ = _parse_type_(d.pop("type", UNSET))

        def _parse_text(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        text = _parse_text(d.pop("text", UNSET))

        def _parse_image_url(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        image_url = _parse_image_url(d.pop("image_url", UNSET))

        def _parse_detail(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        detail = _parse_detail(d.pop("detail", UNSET))

        codex_content_item = cls(
            type_=type_,
            text=text,
            image_url=image_url,
            detail=detail,
        )

        codex_content_item.additional_properties = d
        return codex_content_item

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
