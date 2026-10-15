from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast
from uuid import UUID

from attrs import define as _attrs_define
from typing_extensions import Self

from ..models.session_search_filters_decision_categories_type_0_item import (
    SessionSearchFiltersDecisionCategoriesType0Item,
)
from ..models.session_search_filters_grading_statuses_type_0_item import (
    SessionSearchFiltersGradingStatusesType0Item,
)
from ..models.session_search_filters_review_statuses_type_0_item import (
    SessionSearchFiltersReviewStatusesType0Item,
)
from ..models.session_search_filters_severities_type_0_item import (
    SessionSearchFiltersSeveritiesType0Item,
)
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.session_search_filters_external_ids_type_0 import (
        SessionSearchFiltersExternalIdsType0,
    )
    from ..models.user_filter import UserFilter


T = TypeVar("T", bound="SessionSearchFilters")


@_attrs_define
class SessionSearchFilters:
    """Filters for POST /sessions/search.

    Attributes:
        start_date (datetime.datetime | None | Unset): Include only sessions with activity at or after this datetime. A
            session's recorded span runs from its first through its latest message, so a session still in progress matches
            if it has had activity at or after this time.
        end_date (datetime.datetime | None | Unset): Include only sessions that started on or before this datetime.
        session_id (None | Unset | UUID):
        external_ids (None | SessionSearchFiltersExternalIdsType0 | Unset):
        agent_platforms (list[str] | None | Unset):
        sources (list[str] | None | Unset): Match any selected canonical ingestion source among retained session
            messages. Open set of exact source keys, combined with other filters using AND. The source match covers the full
            session regardless of the date window.
        grading_statuses (list[SessionSearchFiltersGradingStatusesType0Item] | None | Unset):
        categories (list[str] | None | Unset):
        severities (list[SessionSearchFiltersSeveritiesType0Item] | None | Unset):
        review_statuses (list[SessionSearchFiltersReviewStatusesType0Item] | None | Unset):
        decision_categories (list[SessionSearchFiltersDecisionCategoriesType0Item] | None | Unset):
        user_id (None | Unset | UUID):
        users (None | Unset | UserFilter):
        session_id_contains (None | str | Unset):
        session_name_contains (None | str | Unset):
    """

    start_date: datetime.datetime | None | Unset = UNSET
    end_date: datetime.datetime | None | Unset = UNSET
    session_id: None | Unset | UUID = UNSET
    external_ids: None | SessionSearchFiltersExternalIdsType0 | Unset = UNSET
    agent_platforms: list[str] | None | Unset = UNSET
    sources: list[str] | None | Unset = UNSET
    grading_statuses: (
        list[SessionSearchFiltersGradingStatusesType0Item] | None | Unset
    ) = UNSET
    categories: list[str] | None | Unset = UNSET
    severities: list[SessionSearchFiltersSeveritiesType0Item] | None | Unset = UNSET
    review_statuses: (
        list[SessionSearchFiltersReviewStatusesType0Item] | None | Unset
    ) = UNSET
    decision_categories: (
        list[SessionSearchFiltersDecisionCategoriesType0Item] | None | Unset
    ) = UNSET
    user_id: None | Unset | UUID = UNSET
    users: None | Unset | UserFilter = UNSET
    session_id_contains: None | str | Unset = UNSET
    session_name_contains: None | str | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        from ..models.session_search_filters_external_ids_type_0 import (
            SessionSearchFiltersExternalIdsType0,
        )
        from ..models.user_filter import UserFilter

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

        external_ids: dict[str, Any] | None | Unset
        if isinstance(self.external_ids, Unset):
            external_ids = UNSET
        elif isinstance(self.external_ids, SessionSearchFiltersExternalIdsType0):
            external_ids = self.external_ids.to_dict()
        else:
            external_ids = self.external_ids

        agent_platforms: list[str] | None | Unset
        if isinstance(self.agent_platforms, Unset):
            agent_platforms = UNSET
        elif isinstance(self.agent_platforms, list):
            agent_platforms = self.agent_platforms

        else:
            agent_platforms = self.agent_platforms

        sources: list[str] | None | Unset
        if isinstance(self.sources, Unset):
            sources = UNSET
        elif isinstance(self.sources, list):
            sources = self.sources

        else:
            sources = self.sources

        grading_statuses: list[str] | None | Unset
        if isinstance(self.grading_statuses, Unset):
            grading_statuses = UNSET
        elif isinstance(self.grading_statuses, list):
            grading_statuses = []
            for grading_statuses_type_0_item_data in self.grading_statuses:
                grading_statuses_type_0_item = grading_statuses_type_0_item_data.value
                grading_statuses.append(grading_statuses_type_0_item)

        else:
            grading_statuses = self.grading_statuses

        categories: list[str] | None | Unset
        if isinstance(self.categories, Unset):
            categories = UNSET
        elif isinstance(self.categories, list):
            categories = self.categories

        else:
            categories = self.categories

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

        review_statuses: list[str] | None | Unset
        if isinstance(self.review_statuses, Unset):
            review_statuses = UNSET
        elif isinstance(self.review_statuses, list):
            review_statuses = []
            for review_statuses_type_0_item_data in self.review_statuses:
                review_statuses_type_0_item = review_statuses_type_0_item_data.value
                review_statuses.append(review_statuses_type_0_item)

        else:
            review_statuses = self.review_statuses

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

        user_id: None | str | Unset
        if isinstance(self.user_id, Unset):
            user_id = UNSET
        elif isinstance(self.user_id, UUID):
            user_id = str(self.user_id)
        else:
            user_id = self.user_id

        users: dict[str, Any] | None | Unset
        if isinstance(self.users, Unset):
            users = UNSET
        elif isinstance(self.users, UserFilter):
            users = self.users.to_dict()
        else:
            users = self.users

        session_id_contains: None | str | Unset
        if isinstance(self.session_id_contains, Unset):
            session_id_contains = UNSET
        else:
            session_id_contains = self.session_id_contains

        session_name_contains: None | str | Unset
        if isinstance(self.session_name_contains, Unset):
            session_name_contains = UNSET
        else:
            session_name_contains = self.session_name_contains

        field_dict: dict[str, Any] = {}

        field_dict.update({})
        if start_date is not UNSET:
            field_dict["start_date"] = start_date
        if end_date is not UNSET:
            field_dict["end_date"] = end_date
        if session_id is not UNSET:
            field_dict["session_id"] = session_id
        if external_ids is not UNSET:
            field_dict["external_ids"] = external_ids
        if agent_platforms is not UNSET:
            field_dict["agent_platforms"] = agent_platforms
        if sources is not UNSET:
            field_dict["sources"] = sources
        if grading_statuses is not UNSET:
            field_dict["grading_statuses"] = grading_statuses
        if categories is not UNSET:
            field_dict["categories"] = categories
        if severities is not UNSET:
            field_dict["severities"] = severities
        if review_statuses is not UNSET:
            field_dict["review_statuses"] = review_statuses
        if decision_categories is not UNSET:
            field_dict["decision_categories"] = decision_categories
        if user_id is not UNSET:
            field_dict["user_id"] = user_id
        if users is not UNSET:
            field_dict["users"] = users
        if session_id_contains is not UNSET:
            field_dict["session_id_contains"] = session_id_contains
        if session_name_contains is not UNSET:
            field_dict["session_name_contains"] = session_name_contains

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        from ..models.session_search_filters_external_ids_type_0 import (
            SessionSearchFiltersExternalIdsType0,
        )
        from ..models.user_filter import UserFilter

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

        def _parse_external_ids(
            data: object,
        ) -> None | SessionSearchFiltersExternalIdsType0 | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                external_ids_type_0 = SessionSearchFiltersExternalIdsType0.from_dict(
                    data
                )

                return external_ids_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | SessionSearchFiltersExternalIdsType0 | Unset, data)

        external_ids = _parse_external_ids(d.pop("external_ids", UNSET))

        def _parse_agent_platforms(data: object) -> list[str] | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                agent_platforms_type_0 = cast(list[str], data)

                return agent_platforms_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(list[str] | None | Unset, data)

        agent_platforms = _parse_agent_platforms(d.pop("agent_platforms", UNSET))

        def _parse_sources(data: object) -> list[str] | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                sources_type_0 = cast(list[str], data)

                return sources_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(list[str] | None | Unset, data)

        sources = _parse_sources(d.pop("sources", UNSET))

        def _parse_grading_statuses(
            data: object,
        ) -> list[SessionSearchFiltersGradingStatusesType0Item] | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                grading_statuses_type_0 = []
                _grading_statuses_type_0 = data
                for grading_statuses_type_0_item_data in _grading_statuses_type_0:
                    grading_statuses_type_0_item = (
                        SessionSearchFiltersGradingStatusesType0Item(
                            grading_statuses_type_0_item_data
                        )
                    )

                    grading_statuses_type_0.append(grading_statuses_type_0_item)

                return grading_statuses_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(
                list[SessionSearchFiltersGradingStatusesType0Item] | None | Unset, data
            )

        grading_statuses = _parse_grading_statuses(d.pop("grading_statuses", UNSET))

        def _parse_categories(data: object) -> list[str] | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                categories_type_0 = cast(list[str], data)

                return categories_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(list[str] | None | Unset, data)

        categories = _parse_categories(d.pop("categories", UNSET))

        def _parse_severities(
            data: object,
        ) -> list[SessionSearchFiltersSeveritiesType0Item] | None | Unset:
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
                    severities_type_0_item = SessionSearchFiltersSeveritiesType0Item(
                        severities_type_0_item_data
                    )

                    severities_type_0.append(severities_type_0_item)

                return severities_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(
                list[SessionSearchFiltersSeveritiesType0Item] | None | Unset, data
            )

        severities = _parse_severities(d.pop("severities", UNSET))

        def _parse_review_statuses(
            data: object,
        ) -> list[SessionSearchFiltersReviewStatusesType0Item] | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                review_statuses_type_0 = []
                _review_statuses_type_0 = data
                for review_statuses_type_0_item_data in _review_statuses_type_0:
                    review_statuses_type_0_item = (
                        SessionSearchFiltersReviewStatusesType0Item(
                            review_statuses_type_0_item_data
                        )
                    )

                    review_statuses_type_0.append(review_statuses_type_0_item)

                return review_statuses_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(
                list[SessionSearchFiltersReviewStatusesType0Item] | None | Unset, data
            )

        review_statuses = _parse_review_statuses(d.pop("review_statuses", UNSET))

        def _parse_decision_categories(
            data: object,
        ) -> list[SessionSearchFiltersDecisionCategoriesType0Item] | None | Unset:
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
                        SessionSearchFiltersDecisionCategoriesType0Item(
                            decision_categories_type_0_item_data
                        )
                    )

                    decision_categories_type_0.append(decision_categories_type_0_item)

                return decision_categories_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(
                list[SessionSearchFiltersDecisionCategoriesType0Item] | None | Unset,
                data,
            )

        decision_categories = _parse_decision_categories(
            d.pop("decision_categories", UNSET)
        )

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

        def _parse_users(data: object) -> None | Unset | UserFilter:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                users_type_0 = UserFilter.from_dict(data)

                return users_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | Unset | UserFilter, data)

        users = _parse_users(d.pop("users", UNSET))

        def _parse_session_id_contains(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        session_id_contains = _parse_session_id_contains(
            d.pop("session_id_contains", UNSET)
        )

        def _parse_session_name_contains(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        session_name_contains = _parse_session_name_contains(
            d.pop("session_name_contains", UNSET)
        )

        session_search_filters = cls(
            start_date=start_date,
            end_date=end_date,
            session_id=session_id,
            external_ids=external_ids,
            agent_platforms=agent_platforms,
            sources=sources,
            grading_statuses=grading_statuses,
            categories=categories,
            severities=severities,
            review_statuses=review_statuses,
            decision_categories=decision_categories,
            user_id=user_id,
            users=users,
            session_id_contains=session_id_contains,
            session_name_contains=session_name_contains,
        )

        return session_search_filters
