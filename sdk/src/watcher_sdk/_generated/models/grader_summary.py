from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Self, TypeVar, cast
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.grader_summary_scores import GraderSummaryScores


T = TypeVar("T", bound="GraderSummary")


@_attrs_define
class GraderSummary:
    """Grader in list responses (no header/footer).

    Graders are always self-describing rows: the graders API never serves the
    server-managed monitors' identity rows (those surface via /v1/monitors).

        Attributes:
            grader_id (UUID):
            version (int):
            organization_id (str):
            name (str):
            description (None | str):
            scores (GraderSummaryScores):
            default_model (None | str):
            created_at (datetime.datetime):
            user_id (None | Unset | UUID):
            public (bool | Unset):  Default: True.
    """

    grader_id: UUID
    version: int
    organization_id: str
    name: str
    description: None | str
    scores: GraderSummaryScores
    default_model: None | str
    created_at: datetime.datetime
    user_id: None | Unset | UUID = UNSET
    public: bool | Unset = True
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        grader_id = str(self.grader_id)

        version = self.version

        organization_id = self.organization_id

        name = self.name

        description: None | str
        description = self.description

        scores = self.scores.to_dict()

        default_model: None | str
        default_model = self.default_model

        created_at = self.created_at.isoformat()

        user_id: None | str | Unset
        if isinstance(self.user_id, Unset):
            user_id = UNSET
        elif isinstance(self.user_id, UUID):
            user_id = str(self.user_id)
        else:
            user_id = self.user_id

        public = self.public

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "grader_id": grader_id,
                "version": version,
                "organization_id": organization_id,
                "name": name,
                "description": description,
                "scores": scores,
                "default_model": default_model,
                "created_at": created_at,
            }
        )
        if user_id is not UNSET:
            field_dict["user_id"] = user_id
        if public is not UNSET:
            field_dict["public"] = public

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        from ..models.grader_summary_scores import GraderSummaryScores

        d = dict(src_dict)
        grader_id = UUID(d.pop("grader_id"))

        version = d.pop("version")

        organization_id = d.pop("organization_id")

        name = d.pop("name")

        def _parse_description(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        description = _parse_description(d.pop("description"))

        scores = GraderSummaryScores.from_dict(d.pop("scores"))

        def _parse_default_model(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        default_model = _parse_default_model(d.pop("default_model"))

        created_at = datetime.datetime.fromisoformat(d.pop("created_at"))

        def _parse_user_id(data: object) -> None | Unset | UUID:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                user_id_type_0 = UUID(data)

                return user_id_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | Unset | UUID, data)

        user_id = _parse_user_id(d.pop("user_id", UNSET))

        public = d.pop("public", UNSET)

        grader_summary = cls(
            grader_id=grader_id,
            version=version,
            organization_id=organization_id,
            name=name,
            description=description,
            scores=scores,
            default_model=default_model,
            created_at=created_at,
            user_id=user_id,
            public=public,
        )

        grader_summary.additional_properties = d
        return grader_summary

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
