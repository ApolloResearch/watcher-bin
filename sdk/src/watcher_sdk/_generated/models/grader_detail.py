from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from typing_extensions import Self

from ..models.grader_detail_reasoning_effort_type_0 import (
    GraderDetailReasoningEffortType0,
)
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.grader_detail_scores import GraderDetailScores


T = TypeVar("T", bound="GraderDetail")


@_attrs_define
class GraderDetail:
    """Full grader detail including header, footer, and output configuration flags.

    Graders are always self-describing rows: the graders API never serves the
    server-managed monitors' identity rows (those surface via /v1/monitors).

        Attributes:
            grader_id (UUID):
            version (int):
            organization_id (str):
            name (str):
            description (None | str):
            header (str):
            footer (None | str):
            scores (GraderDetailScores):
            default_model (None | str):
            include_thinking (bool):
            include_explanation (bool):
            include_summary (bool):
            created_at (datetime.datetime):
            user_id (None | Unset | UUID):
            public (bool | Unset):  Default: True.
            reasoning_effort (GraderDetailReasoningEffortType0 | None | Unset):
            reasoning_tokens (int | None | Unset):
    """

    grader_id: UUID
    version: int
    organization_id: str
    name: str
    description: None | str
    header: str
    footer: None | str
    scores: GraderDetailScores
    default_model: None | str
    include_thinking: bool
    include_explanation: bool
    include_summary: bool
    created_at: datetime.datetime
    user_id: None | Unset | UUID = UNSET
    public: bool | Unset = True
    reasoning_effort: GraderDetailReasoningEffortType0 | None | Unset = UNSET
    reasoning_tokens: int | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        grader_id = str(self.grader_id)

        version = self.version

        organization_id = self.organization_id

        name = self.name

        description: None | str
        description = self.description

        header = self.header

        footer: None | str
        footer = self.footer

        scores = self.scores.to_dict()

        default_model: None | str
        default_model = self.default_model

        include_thinking = self.include_thinking

        include_explanation = self.include_explanation

        include_summary = self.include_summary

        created_at = self.created_at.isoformat()

        user_id: None | str | Unset
        if isinstance(self.user_id, Unset):
            user_id = UNSET
        elif isinstance(self.user_id, UUID):
            user_id = str(self.user_id)
        else:
            user_id = self.user_id

        public = self.public

        reasoning_effort: None | str | Unset
        if isinstance(self.reasoning_effort, Unset):
            reasoning_effort = UNSET
        elif isinstance(self.reasoning_effort, GraderDetailReasoningEffortType0):
            reasoning_effort = self.reasoning_effort.value
        else:
            reasoning_effort = self.reasoning_effort

        reasoning_tokens: int | None | Unset
        if isinstance(self.reasoning_tokens, Unset):
            reasoning_tokens = UNSET
        else:
            reasoning_tokens = self.reasoning_tokens

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "grader_id": grader_id,
                "version": version,
                "organization_id": organization_id,
                "name": name,
                "description": description,
                "header": header,
                "footer": footer,
                "scores": scores,
                "default_model": default_model,
                "include_thinking": include_thinking,
                "include_explanation": include_explanation,
                "include_summary": include_summary,
                "created_at": created_at,
            }
        )
        if user_id is not UNSET:
            field_dict["user_id"] = user_id
        if public is not UNSET:
            field_dict["public"] = public
        if reasoning_effort is not UNSET:
            field_dict["reasoning_effort"] = reasoning_effort
        if reasoning_tokens is not UNSET:
            field_dict["reasoning_tokens"] = reasoning_tokens

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        from ..models.grader_detail_scores import GraderDetailScores

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

        header = d.pop("header")

        def _parse_footer(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        footer = _parse_footer(d.pop("footer"))

        scores = GraderDetailScores.from_dict(d.pop("scores"))

        def _parse_default_model(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        default_model = _parse_default_model(d.pop("default_model"))

        include_thinking = d.pop("include_thinking")

        include_explanation = d.pop("include_explanation")

        include_summary = d.pop("include_summary")

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

        def _parse_reasoning_effort(
            data: object,
        ) -> GraderDetailReasoningEffortType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                reasoning_effort_type_0 = GraderDetailReasoningEffortType0(data)

                return reasoning_effort_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(GraderDetailReasoningEffortType0 | None | Unset, data)

        reasoning_effort = _parse_reasoning_effort(d.pop("reasoning_effort", UNSET))

        def _parse_reasoning_tokens(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        reasoning_tokens = _parse_reasoning_tokens(d.pop("reasoning_tokens", UNSET))

        grader_detail = cls(
            grader_id=grader_id,
            version=version,
            organization_id=organization_id,
            name=name,
            description=description,
            header=header,
            footer=footer,
            scores=scores,
            default_model=default_model,
            include_thinking=include_thinking,
            include_explanation=include_explanation,
            include_summary=include_summary,
            created_at=created_at,
            user_id=user_id,
            public=public,
            reasoning_effort=reasoning_effort,
            reasoning_tokens=reasoning_tokens,
        )

        grader_detail.additional_properties = d
        return grader_detail

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
