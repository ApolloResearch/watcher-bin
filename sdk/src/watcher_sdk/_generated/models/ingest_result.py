from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Self, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.ingest_result_status import IngestResultStatus
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.hook_append_anchor import HookAppendAnchor


T = TypeVar("T", bound="IngestResult")


@_attrs_define
class IngestResult:
    """Receipt for one input, in the same position as its uploaded trajectory.

    A null endpoint still occupies a result slot. ``chunk_end`` proves this
    input's stored prefix; ``leaf`` describes its session's latest branch and
    must not be substituted for the acknowledged endpoint.

        Attributes:
            status (IngestResultStatus):
            chunk_end (HookAppendAnchor | None | Unset):
            leaf (HookAppendAnchor | None | Unset):
    """

    status: IngestResultStatus
    chunk_end: HookAppendAnchor | None | Unset = UNSET
    leaf: HookAppendAnchor | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.hook_append_anchor import HookAppendAnchor

        status = self.status.value

        chunk_end: dict[str, Any] | None | Unset
        if isinstance(self.chunk_end, Unset):
            chunk_end = UNSET
        elif isinstance(self.chunk_end, HookAppendAnchor):
            chunk_end = self.chunk_end.to_dict()
        else:
            chunk_end = self.chunk_end

        leaf: dict[str, Any] | None | Unset
        if isinstance(self.leaf, Unset):
            leaf = UNSET
        elif isinstance(self.leaf, HookAppendAnchor):
            leaf = self.leaf.to_dict()
        else:
            leaf = self.leaf

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "status": status,
            }
        )
        if chunk_end is not UNSET:
            field_dict["chunk_end"] = chunk_end
        if leaf is not UNSET:
            field_dict["leaf"] = leaf

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        from ..models.hook_append_anchor import HookAppendAnchor

        d = dict(src_dict)
        status = IngestResultStatus(d.pop("status"))

        def _parse_chunk_end(data: object) -> HookAppendAnchor | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                chunk_end_type_0 = HookAppendAnchor.from_dict(data)

                return chunk_end_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(HookAppendAnchor | None | Unset, data)

        chunk_end = _parse_chunk_end(d.pop("chunk_end", UNSET))

        def _parse_leaf(data: object) -> HookAppendAnchor | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                leaf_type_0 = HookAppendAnchor.from_dict(data)

                return leaf_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(HookAppendAnchor | None | Unset, data)

        leaf = _parse_leaf(d.pop("leaf", UNSET))

        ingest_result = cls(
            status=status,
            chunk_end=chunk_end,
            leaf=leaf,
        )

        ingest_result.additional_properties = d
        return ingest_result

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
