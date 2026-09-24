from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define

from ..models.update_grader_request_reasoning_effort_type_0 import (
    UpdateGraderRequestReasoningEffortType0,
)
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.update_grader_request_scores_type_0 import (
        UpdateGraderRequestScoresType0,
    )


T = TypeVar("T", bound="UpdateGraderRequest")


@_attrs_define
class UpdateGraderRequest:
    """Request body for PATCH /v1/graders/{grader_id}.

    PATCH creates a new grader version instead of mutating. All fields are optional;
    only fields present in the request JSON are merged into the new version.

        Attributes:
            name (None | str | Unset):
            description (None | str | Unset):
            header (None | str | Unset):
            footer (None | str | Unset):
            scores (None | Unset | UpdateGraderRequestScoresType0):
            default_model (None | str | Unset):
            include_thinking (bool | None | Unset):
            include_explanation (bool | None | Unset):
            include_summary (bool | None | Unset):
            reasoning_effort (None | Unset | UpdateGraderRequestReasoningEffortType0):
            reasoning_tokens (int | None | Unset):
            public (bool | None | Unset):
    """

    name: None | str | Unset = UNSET
    description: None | str | Unset = UNSET
    header: None | str | Unset = UNSET
    footer: None | str | Unset = UNSET
    scores: None | Unset | UpdateGraderRequestScoresType0 = UNSET
    default_model: None | str | Unset = UNSET
    include_thinking: bool | None | Unset = UNSET
    include_explanation: bool | None | Unset = UNSET
    include_summary: bool | None | Unset = UNSET
    reasoning_effort: None | Unset | UpdateGraderRequestReasoningEffortType0 = UNSET
    reasoning_tokens: int | None | Unset = UNSET
    public: bool | None | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        from ..models.update_grader_request_scores_type_0 import (
            UpdateGraderRequestScoresType0,
        )

        name: None | str | Unset
        if isinstance(self.name, Unset):
            name = UNSET
        else:
            name = self.name

        description: None | str | Unset
        if isinstance(self.description, Unset):
            description = UNSET
        else:
            description = self.description

        header: None | str | Unset
        if isinstance(self.header, Unset):
            header = UNSET
        else:
            header = self.header

        footer: None | str | Unset
        if isinstance(self.footer, Unset):
            footer = UNSET
        else:
            footer = self.footer

        scores: dict[str, Any] | None | Unset
        if isinstance(self.scores, Unset):
            scores = UNSET
        elif isinstance(self.scores, UpdateGraderRequestScoresType0):
            scores = self.scores.to_dict()
        else:
            scores = self.scores

        default_model: None | str | Unset
        if isinstance(self.default_model, Unset):
            default_model = UNSET
        else:
            default_model = self.default_model

        include_thinking: bool | None | Unset
        if isinstance(self.include_thinking, Unset):
            include_thinking = UNSET
        else:
            include_thinking = self.include_thinking

        include_explanation: bool | None | Unset
        if isinstance(self.include_explanation, Unset):
            include_explanation = UNSET
        else:
            include_explanation = self.include_explanation

        include_summary: bool | None | Unset
        if isinstance(self.include_summary, Unset):
            include_summary = UNSET
        else:
            include_summary = self.include_summary

        reasoning_effort: None | str | Unset
        if isinstance(self.reasoning_effort, Unset):
            reasoning_effort = UNSET
        elif isinstance(self.reasoning_effort, UpdateGraderRequestReasoningEffortType0):
            reasoning_effort = self.reasoning_effort.value
        else:
            reasoning_effort = self.reasoning_effort

        reasoning_tokens: int | None | Unset
        if isinstance(self.reasoning_tokens, Unset):
            reasoning_tokens = UNSET
        else:
            reasoning_tokens = self.reasoning_tokens

        public: bool | None | Unset
        if isinstance(self.public, Unset):
            public = UNSET
        else:
            public = self.public

        field_dict: dict[str, Any] = {}

        field_dict.update({})
        if name is not UNSET:
            field_dict["name"] = name
        if description is not UNSET:
            field_dict["description"] = description
        if header is not UNSET:
            field_dict["header"] = header
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
        from ..models.update_grader_request_scores_type_0 import (
            UpdateGraderRequestScoresType0,
        )

        d = dict(src_dict)

        def _parse_name(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        name = _parse_name(d.pop("name", UNSET))

        def _parse_description(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        description = _parse_description(d.pop("description", UNSET))

        def _parse_header(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        header = _parse_header(d.pop("header", UNSET))

        def _parse_footer(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        footer = _parse_footer(d.pop("footer", UNSET))

        def _parse_scores(
            data: object,
        ) -> None | Unset | UpdateGraderRequestScoresType0:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                scores_type_0 = UpdateGraderRequestScoresType0.from_dict(data)

                return scores_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | Unset | UpdateGraderRequestScoresType0, data)

        scores = _parse_scores(d.pop("scores", UNSET))

        def _parse_default_model(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        default_model = _parse_default_model(d.pop("default_model", UNSET))

        def _parse_include_thinking(data: object) -> bool | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(bool | None | Unset, data)

        include_thinking = _parse_include_thinking(d.pop("include_thinking", UNSET))

        def _parse_include_explanation(data: object) -> bool | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(bool | None | Unset, data)

        include_explanation = _parse_include_explanation(
            d.pop("include_explanation", UNSET)
        )

        def _parse_include_summary(data: object) -> bool | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(bool | None | Unset, data)

        include_summary = _parse_include_summary(d.pop("include_summary", UNSET))

        def _parse_reasoning_effort(
            data: object,
        ) -> None | Unset | UpdateGraderRequestReasoningEffortType0:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                reasoning_effort_type_0 = UpdateGraderRequestReasoningEffortType0(data)

                return reasoning_effort_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | Unset | UpdateGraderRequestReasoningEffortType0, data)

        reasoning_effort = _parse_reasoning_effort(d.pop("reasoning_effort", UNSET))

        def _parse_reasoning_tokens(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        reasoning_tokens = _parse_reasoning_tokens(d.pop("reasoning_tokens", UNSET))

        def _parse_public(data: object) -> bool | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(bool | None | Unset, data)

        public = _parse_public(d.pop("public", UNSET))

        update_grader_request = cls(
            name=name,
            description=description,
            header=header,
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

        return update_grader_request
