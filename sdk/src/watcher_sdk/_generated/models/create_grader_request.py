from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define

from ..models.create_grader_request_reasoning_effort_type_0 import (
    CreateGraderRequestReasoningEffortType0,
)
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.create_grader_request_scores import CreateGraderRequestScores


T = TypeVar("T", bound="CreateGraderRequest")


@_attrs_define
class CreateGraderRequest:
    """Request body for POST /v1/graders.

    Attributes:
        name (str):
        header (str):
        description (None | str | Unset):
        footer (None | str | Unset):
        scores (CreateGraderRequestScores | Unset):
        default_model (None | str | Unset):
        include_thinking (bool | Unset):  Default: True.
        include_explanation (bool | Unset):  Default: True.
        include_summary (bool | Unset):  Default: True.
        reasoning_effort (CreateGraderRequestReasoningEffortType0 | None | Unset):
        reasoning_tokens (int | None | Unset):
        public (bool | Unset):  Default: False.
    """

    name: str
    header: str
    description: None | str | Unset = UNSET
    footer: None | str | Unset = UNSET
    scores: CreateGraderRequestScores | Unset = UNSET
    default_model: None | str | Unset = UNSET
    include_thinking: bool | Unset = True
    include_explanation: bool | Unset = True
    include_summary: bool | Unset = True
    reasoning_effort: CreateGraderRequestReasoningEffortType0 | None | Unset = UNSET
    reasoning_tokens: int | None | Unset = UNSET
    public: bool | Unset = False

    def to_dict(self) -> dict[str, Any]:
        name = self.name

        header = self.header

        description: None | str | Unset
        if isinstance(self.description, Unset):
            description = UNSET
        else:
            description = self.description

        footer: None | str | Unset
        if isinstance(self.footer, Unset):
            footer = UNSET
        else:
            footer = self.footer

        scores: dict[str, Any] | Unset = UNSET
        if not isinstance(self.scores, Unset):
            scores = self.scores.to_dict()

        default_model: None | str | Unset
        if isinstance(self.default_model, Unset):
            default_model = UNSET
        else:
            default_model = self.default_model

        include_thinking = self.include_thinking

        include_explanation = self.include_explanation

        include_summary = self.include_summary

        reasoning_effort: None | str | Unset
        if isinstance(self.reasoning_effort, Unset):
            reasoning_effort = UNSET
        elif isinstance(self.reasoning_effort, CreateGraderRequestReasoningEffortType0):
            reasoning_effort = self.reasoning_effort.value
        else:
            reasoning_effort = self.reasoning_effort

        reasoning_tokens: int | None | Unset
        if isinstance(self.reasoning_tokens, Unset):
            reasoning_tokens = UNSET
        else:
            reasoning_tokens = self.reasoning_tokens

        public = self.public

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "name": name,
                "header": header,
            }
        )
        if description is not UNSET:
            field_dict["description"] = description
        if footer is not UNSET:
            field_dict["footer"] = footer
        if scores is not UNSET:
            field_dict["scores"] = scores
        if default_model is not UNSET:
            field_dict["default_model"] = default_model
        if include_thinking is not UNSET:
            field_dict["include_thinking"] = include_thinking
        if include_explanation is not UNSET:
            field_dict["include_explanation"] = include_explanation
        if include_summary is not UNSET:
            field_dict["include_summary"] = include_summary
        if reasoning_effort is not UNSET:
            field_dict["reasoning_effort"] = reasoning_effort
        if reasoning_tokens is not UNSET:
            field_dict["reasoning_tokens"] = reasoning_tokens
        if public is not UNSET:
            field_dict["public"] = public

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.create_grader_request_scores import CreateGraderRequestScores

        d = dict(src_dict)
        name = d.pop("name")

        header = d.pop("header")

        def _parse_description(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        description = _parse_description(d.pop("description", UNSET))

        def _parse_footer(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        footer = _parse_footer(d.pop("footer", UNSET))

        _scores = d.pop("scores", UNSET)
        scores: CreateGraderRequestScores | Unset
        if isinstance(_scores, Unset):
            scores = UNSET
        else:
            scores = CreateGraderRequestScores.from_dict(_scores)

        def _parse_default_model(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        default_model = _parse_default_model(d.pop("default_model", UNSET))

        include_thinking = d.pop("include_thinking", UNSET)

        include_explanation = d.pop("include_explanation", UNSET)

        include_summary = d.pop("include_summary", UNSET)

        def _parse_reasoning_effort(
            data: object,
        ) -> CreateGraderRequestReasoningEffortType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                reasoning_effort_type_0 = CreateGraderRequestReasoningEffortType0(data)

                return reasoning_effort_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(CreateGraderRequestReasoningEffortType0 | None | Unset, data)

        reasoning_effort = _parse_reasoning_effort(d.pop("reasoning_effort", UNSET))

        def _parse_reasoning_tokens(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        reasoning_tokens = _parse_reasoning_tokens(d.pop("reasoning_tokens", UNSET))

        public = d.pop("public", UNSET)

        create_grader_request = cls(
            name=name,
            header=header,
            description=description,
            footer=footer,
            scores=scores,
            default_model=default_model,
            include_thinking=include_thinking,
            include_explanation=include_explanation,
            include_summary=include_summary,
            reasoning_effort=reasoning_effort,
            reasoning_tokens=reasoning_tokens,
            public=public,
        )

        return create_grader_request
