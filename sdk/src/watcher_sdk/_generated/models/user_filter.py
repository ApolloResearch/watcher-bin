from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Self, TypeVar
from uuid import UUID

from attrs import define as _attrs_define

from ..models.user_filter_mode import UserFilterMode

T = TypeVar("T", bound="UserFilter")


@_attrs_define
class UserFilter:
    """Include or exclude selected owners within the caller's session read scope.

    Both fields are required; omit the entire filter to select all permitted
    owners. Include matches any listed owner; exclude removes all listed owners
    and retains unattributed sessions. Unknown UUIDs match nothing in include
    mode and remove nothing in exclude mode. Duplicate IDs are removed while
    preserving their first occurrence, including in serialized audit records.
    This selection never grants permission to read the selected owners' data.

        Attributes:
            ids (list[UUID]):
            mode (UserFilterMode):
    """

    ids: list[UUID]
    mode: UserFilterMode

    def to_dict(self) -> dict[str, Any]:
        ids = []
        for ids_item_data in self.ids:
            ids_item = str(ids_item_data)
            ids.append(ids_item)

        mode = self.mode.value

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "ids": ids,
                "mode": mode,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        d = dict(src_dict)
        ids = []
        _ids = d.pop("ids")
        for ids_item_data in _ids:
            ids_item = UUID(ids_item_data)

            ids.append(ids_item)

        mode = UserFilterMode(d.pop("mode"))

        user_filter = cls(
            ids=ids,
            mode=mode,
        )

        return user_filter
