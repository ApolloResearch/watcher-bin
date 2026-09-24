from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.grading_usage_response_bucket import GradingUsageResponseBucket

if TYPE_CHECKING:
    from ..models.grading_usage_breakdown_row import GradingUsageBreakdownRow
    from ..models.grading_usage_bucket import GradingUsageBucket
    from ..models.grading_usage_cost_bucket import GradingUsageCostBucket
    from ..models.grading_usage_filter_options import GradingUsageFilterOptions


T = TypeVar("T", bound="GradingUsageResponse")


@_attrs_define
class GradingUsageResponse:
    """Grading usage aggregates from GET /v1/usage/grading.

    ``by_date`` holds one row per time bucket, ordered by date ascending;
    ``by_date_cost`` mirrors it with estimated USD spend per request kind
    (empty when token details are hidden), and ``unpriced_models`` lists
    models whose usage is excluded from cost estimates for lack of rates.
    ``by_user``/``by_model``/``by_grader`` hold window totals per breakdown
    value, ordered by output tokens descending. ``token_details_enabled``
    reports whether this deployment exposes raw token counts; when false, all
    token fields are null and only request counts are meaningful.

        Attributes:
            token_details_enabled (bool):
            bucket (GradingUsageResponseBucket):
            by_date (list[GradingUsageBucket]):
            by_date_cost (list[GradingUsageCostBucket]):
            unpriced_models (list[str]):
            by_user (list[GradingUsageBreakdownRow]):
            by_model (list[GradingUsageBreakdownRow]):
            by_grader (list[GradingUsageBreakdownRow]):
            options (GradingUsageFilterOptions): Distinct filterable values for the grading-usage view.

                ``users`` and ``graders`` are org-wide; ``models`` only includes models
                with usage inside the requested date window, so the picker never offers a
                model that would chart nothing.
    """

    token_details_enabled: bool
    bucket: GradingUsageResponseBucket
    by_date: list[GradingUsageBucket]
    by_date_cost: list[GradingUsageCostBucket]
    unpriced_models: list[str]
    by_user: list[GradingUsageBreakdownRow]
    by_model: list[GradingUsageBreakdownRow]
    by_grader: list[GradingUsageBreakdownRow]
    options: GradingUsageFilterOptions
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        token_details_enabled = self.token_details_enabled

        bucket = self.bucket.value

        by_date = []
        for by_date_item_data in self.by_date:
            by_date_item = by_date_item_data.to_dict()
            by_date.append(by_date_item)

        by_date_cost = []
        for by_date_cost_item_data in self.by_date_cost:
            by_date_cost_item = by_date_cost_item_data.to_dict()
            by_date_cost.append(by_date_cost_item)

        unpriced_models = self.unpriced_models

        by_user = []
        for by_user_item_data in self.by_user:
            by_user_item = by_user_item_data.to_dict()
            by_user.append(by_user_item)

        by_model = []
        for by_model_item_data in self.by_model:
            by_model_item = by_model_item_data.to_dict()
            by_model.append(by_model_item)

        by_grader = []
        for by_grader_item_data in self.by_grader:
            by_grader_item = by_grader_item_data.to_dict()
            by_grader.append(by_grader_item)

        options = self.options.to_dict()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "token_details_enabled": token_details_enabled,
                "bucket": bucket,
                "by_date": by_date,
                "by_date_cost": by_date_cost,
                "unpriced_models": unpriced_models,
                "by_user": by_user,
                "by_model": by_model,
                "by_grader": by_grader,
                "options": options,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.grading_usage_breakdown_row import GradingUsageBreakdownRow
        from ..models.grading_usage_bucket import GradingUsageBucket
        from ..models.grading_usage_cost_bucket import GradingUsageCostBucket
        from ..models.grading_usage_filter_options import GradingUsageFilterOptions

        d = dict(src_dict)
        token_details_enabled = d.pop("token_details_enabled")

        bucket = GradingUsageResponseBucket(d.pop("bucket"))

        by_date = []
        _by_date = d.pop("by_date")
        for by_date_item_data in _by_date:
            by_date_item = GradingUsageBucket.from_dict(by_date_item_data)

            by_date.append(by_date_item)

        by_date_cost = []
        _by_date_cost = d.pop("by_date_cost")
        for by_date_cost_item_data in _by_date_cost:
            by_date_cost_item = GradingUsageCostBucket.from_dict(by_date_cost_item_data)

            by_date_cost.append(by_date_cost_item)

        unpriced_models = cast(list[str], d.pop("unpriced_models"))

        by_user = []
        _by_user = d.pop("by_user")
        for by_user_item_data in _by_user:
            by_user_item = GradingUsageBreakdownRow.from_dict(by_user_item_data)

            by_user.append(by_user_item)

        by_model = []
        _by_model = d.pop("by_model")
        for by_model_item_data in _by_model:
            by_model_item = GradingUsageBreakdownRow.from_dict(by_model_item_data)

            by_model.append(by_model_item)

        by_grader = []
        _by_grader = d.pop("by_grader")
        for by_grader_item_data in _by_grader:
            by_grader_item = GradingUsageBreakdownRow.from_dict(by_grader_item_data)

            by_grader.append(by_grader_item)

        options = GradingUsageFilterOptions.from_dict(d.pop("options"))

        grading_usage_response = cls(
            token_details_enabled=token_details_enabled,
            bucket=bucket,
            by_date=by_date,
            by_date_cost=by_date_cost,
            unpriced_models=unpriced_models,
            by_user=by_user,
            by_model=by_model,
            by_grader=by_grader,
            options=options,
        )

        grading_usage_response.additional_properties = d
        return grading_usage_response

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
