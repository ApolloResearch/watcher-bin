from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import Any, TypeVar, cast
from uuid import UUID

from attrs import define as _attrs_define
from typing_extensions import Self

from ..models.tool_call_search_filters_decision_categories_type_0_item import (
    ToolCallSearchFiltersDecisionCategoriesType0Item,
)
from ..models.tool_call_search_filters_severities_type_0_item import (
    ToolCallSearchFiltersSeveritiesType0Item,
)
from ..types import UNSET, Unset

T = TypeVar("T", bound="ToolCallSearchFilters")


@_attrs_define
class ToolCallSearchFilters:
    """Filter options for the tool-call list. Every field is optional and ANDed.

    Attributes:
        start_date (datetime.datetime | None | Unset): Include only tool calls whose message was recorded at or after
            this time. Calls are dated by their own message rather than by their session's span, so a session running across
            the boundary contributes only the calls inside it.
        end_date (datetime.datetime | None | Unset): Include only tool calls whose message was recorded at or before
            this time.
        session_id (None | Unset | UUID): Restrict results to one session.
        user_id (None | Unset | UUID): Restrict results to one user. Callers without sessions:findings:read:any may only
            name themselves.
        tool_names (list[str] | None | Unset): Tool names to match with OR semantics. Unknown names are valid and match
            no calls.
        severities (list[ToolCallSearchFiltersSeveritiesType0Item] | None | Unset): Score bands to match with OR
            semantics, plus not_scored for calls with no usable gateway or triage score.
        decision_categories (list[ToolCallSearchFiltersDecisionCategoriesType0Item] | None | Unset): Permission outcomes
            to match with OR semantics. Cleared selects calls Watcher allowed without asking.
    """

    start_date: datetime.datetime | None | Unset = UNSET
    end_date: datetime.datetime | None | Unset = UNSET
    session_id: None | Unset | UUID = UNSET
    user_id: None | Unset | UUID = UNSET
    tool_names: list[str] | None | Unset = UNSET
    severities: list[ToolCallSearchFiltersSeveritiesType0Item] | None | Unset = UNSET
    decision_categories: (
        list[ToolCallSearchFiltersDecisionCategoriesType0Item] | None | Unset
    ) = UNSET

    def to_dict(self) -> dict[str, Any]:
        start_date: None | str | Unset
        if isinstance(self.start_date, Unset):
            start_date = UNSET
        elif isinstance(self.start_date, datetime.datetime):
            start_date = self.start_date.isoformat()
        else:
            start_date = self.start_date

        end_date: None | str | Unset
        if isinstance(self.end_date, Unset):
            end_date = UNSET
        elif isinstance(self.end_date, datetime.datetime):
            end_date = self.end_date.isoformat()
        else:
            end_date = self.end_date

        session_id: None | str | Unset
        if isinstance(self.session_id, Unset):
            session_id = UNSET
        elif isinstance(self.session_id, UUID):
            session_id = str(self.session_id)
        else:
            session_id = self.session_id

        user_id: None | str | Unset
        if isinstance(self.user_id, Unset):
            user_id = UNSET
        elif isinstance(self.user_id, UUID):
            user_id = str(self.user_id)
        else:
            user_id = self.user_id

        tool_names: list[str] | None | Unset
        if isinstance(self.tool_names, Unset):
            tool_names = UNSET
        elif isinstance(self.tool_names, list):
            tool_names = self.tool_names

        else:
            tool_names = self.tool_names

        severities: list[str] | None | Unset
        if isinstance(self.severities, Unset):
            severities = UNSET
        elif isinstance(self.severities, list):
            severities = []
            for severities_type_0_item_data in self.severities:
                severities_type_0_item = severities_type_0_item_data.value
                severities.append(severities_type_0_item)

        else:
            severities = self.severities

        decision_categories: list[str] | None | Unset
        if isinstance(self.decision_categories, Unset):
            decision_categories = UNSET
        elif isinstance(self.decision_categories, list):
            decision_categories = []
            for decision_categories_type_0_item_data in self.decision_categories:
                decision_categories_type_0_item = (
                    decision_categories_type_0_item_data.value
                )
                decision_categories.append(decision_categories_type_0_item)

        else:
            decision_categories = self.decision_categories

        field_dict: dict[str, Any] = {}

        field_dict.update({})
        if start_date is not UNSET:
            field_dict["start_date"] = start_date
        if end_date is not UNSET:
            field_dict["end_date"] = end_date
        if session_id is not UNSET:
            field_dict["session_id"] = session_id
        if user_id is not UNSET:
            field_dict["user_id"] = user_id
        if tool_names is not UNSET:
            field_dict["tool_names"] = tool_names
        if severities is not UNSET:
            field_dict["severities"] = severities
        if decision_categories is not UNSET:
            field_dict["decision_categories"] = decision_categories

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        d = dict(src_dict)

        def _parse_start_date(data: object) -> datetime.datetime | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                start_date_type_0 = datetime.datetime.fromisoformat(data)

                return start_date_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None | Unset, data)

        start_date = _parse_start_date(d.pop("start_date", UNSET))

        def _parse_end_date(data: object) -> datetime.datetime | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                end_date_type_0 = datetime.datetime.fromisoformat(data)

                return end_date_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None | Unset, data)

        end_date = _parse_end_date(d.pop("end_date", UNSET))

        def _parse_session_id(data: object) -> None | Unset | UUID:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                session_id_type_0 = UUID(data)

                return session_id_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | Unset | UUID, data)

        session_id = _parse_session_id(d.pop("session_id", UNSET))

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

        def _parse_tool_names(data: object) -> list[str] | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                tool_names_type_0 = cast(list[str], data)

                return tool_names_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(list[str] | None | Unset, data)

        tool_names = _parse_tool_names(d.pop("tool_names", UNSET))

        def _parse_severities(
            data: object,
        ) -> list[ToolCallSearchFiltersSeveritiesType0Item] | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                severities_type_0 = []
                _severities_type_0 = data
                for severities_type_0_item_data in _severities_type_0:
                    severities_type_0_item = ToolCallSearchFiltersSeveritiesType0Item(
                        severities_type_0_item_data
                    )

                    severities_type_0.append(severities_type_0_item)

                return severities_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(
                list[ToolCallSearchFiltersSeveritiesType0Item] | None | Unset, data
            )

        severities = _parse_severities(d.pop("severities", UNSET))

        def _parse_decision_categories(
            data: object,
        ) -> list[ToolCallSearchFiltersDecisionCategoriesType0Item] | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                decision_categories_type_0 = []
                _decision_categories_type_0 = data
                for decision_categories_type_0_item_data in _decision_categories_type_0:
                    decision_categories_type_0_item = (
                        ToolCallSearchFiltersDecisionCategoriesType0Item(
                            decision_categories_type_0_item_data
                        )
                    )

                    decision_categories_type_0.append(decision_categories_type_0_item)

                return decision_categories_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(
                list[ToolCallSearchFiltersDecisionCategoriesType0Item] | None | Unset,
                data,
            )

        decision_categories = _parse_decision_categories(
            d.pop("decision_categories", UNSET)
        )

        tool_call_search_filters = cls(
            start_date=start_date,
            end_date=end_date,
            session_id=session_id,
            user_id=user_id,
            tool_names=tool_names,
            severities=severities,
            decision_categories=decision_categories,
        )

        return tool_call_search_filters
