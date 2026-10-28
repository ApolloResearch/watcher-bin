from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Self, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.copilot_entry_data_type_0 import CopilotEntryDataType0


T = TypeVar("T", bound="CopilotEntry")


@_attrs_define
class CopilotEntry:
    """One event from a GitHub Copilot CLI session log, after the client's selection and shrinking.

    Attributes:
        type_ (str):
        id (None | str | Unset):
        timestamp (None | str | Unset):
        parent_id (None | str | Unset):
        agent_id (None | str | Unset):
        data (CopilotEntryDataType0 | None | Unset):
    """

    type_: str
    id: None | str | Unset = UNSET
    timestamp: None | str | Unset = UNSET
    parent_id: None | str | Unset = UNSET
    agent_id: None | str | Unset = UNSET
    data: CopilotEntryDataType0 | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.copilot_entry_data_type_0 import CopilotEntryDataType0

        type_ = self.type_

        id: None | str | Unset
        if isinstance(self.id, Unset):
            id = UNSET
        else:
            id = self.id

        timestamp: None | str | Unset
        if isinstance(self.timestamp, Unset):
            timestamp = UNSET
        else:
            timestamp = self.timestamp

        parent_id: None | str | Unset
        if isinstance(self.parent_id, Unset):
            parent_id = UNSET
        else:
            parent_id = self.parent_id

        agent_id: None | str | Unset
        if isinstance(self.agent_id, Unset):
            agent_id = UNSET
        else:
            agent_id = self.agent_id

        data: dict[str, Any] | None | Unset
        if isinstance(self.data, Unset):
            data = UNSET
        elif isinstance(self.data, CopilotEntryDataType0):
            data = self.data.to_dict()
        else:
            data = self.data

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "type": type_,
            }
        )
        if id is not UNSET:
            field_dict["id"] = id
        if timestamp is not UNSET:
            field_dict["timestamp"] = timestamp
        if parent_id is not UNSET:
            field_dict["parentId"] = parent_id
        if agent_id is not UNSET:
            field_dict["agentId"] = agent_id
        if data is not UNSET:
            field_dict["data"] = data

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        from ..models.copilot_entry_data_type_0 import CopilotEntryDataType0

        d = dict(src_dict)
        type_ = d.pop("type")

        def _parse_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        id = _parse_id(d.pop("id", UNSET))

        def _parse_timestamp(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        timestamp = _parse_timestamp(d.pop("timestamp", UNSET))

        def _parse_parent_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        parent_id = _parse_parent_id(d.pop("parentId", UNSET))

        def _parse_agent_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        agent_id = _parse_agent_id(d.pop("agentId", UNSET))

        def _parse_data(data: object) -> CopilotEntryDataType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                data_type_0 = CopilotEntryDataType0.from_dict(data)

                return data_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(CopilotEntryDataType0 | None | Unset, data)

        data = _parse_data(d.pop("data", UNSET))

        copilot_entry = cls(
            type_=type_,
            id=id,
            timestamp=timestamp,
            parent_id=parent_id,
            agent_id=agent_id,
            data=data,
        )

        copilot_entry.additional_properties = d
        return copilot_entry

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
