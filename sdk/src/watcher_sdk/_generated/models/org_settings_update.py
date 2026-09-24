from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define

from ..models.org_settings_update_settings_distribution_type_0 import (
    OrgSettingsUpdateSettingsDistributionType0,
)
from ..types import UNSET, Unset

T = TypeVar("T", bound="OrgSettingsUpdate")


@_attrs_define
class OrgSettingsUpdate:
    """Request body for PATCH /v1/org/settings.

    Attributes:
        name (None | str | Unset):
        s3_output_bucket (None | str | Unset):
        s3_output_prefix (None | str | Unset):
        s3_input_prefix (None | str | Unset):
        s3_assume_role_arn (None | str | Unset):
        polling_enabled (bool | None | Unset):
        notifications_enabled (bool | None | Unset):
        flag_threshold (float | None | Unset):
        slack_webhook_url (None | str | Unset):
        session_content_retention_days (int | None | Unset):
        settings_distribution (None | OrgSettingsUpdateSettingsDistributionType0 | Unset):
    """

    name: None | str | Unset = UNSET
    s3_output_bucket: None | str | Unset = UNSET
    s3_output_prefix: None | str | Unset = UNSET
    s3_input_prefix: None | str | Unset = UNSET
    s3_assume_role_arn: None | str | Unset = UNSET
    polling_enabled: bool | None | Unset = UNSET
    notifications_enabled: bool | None | Unset = UNSET
    flag_threshold: float | None | Unset = UNSET
    slack_webhook_url: None | str | Unset = UNSET
    session_content_retention_days: int | None | Unset = UNSET
    settings_distribution: None | OrgSettingsUpdateSettingsDistributionType0 | Unset = (
        UNSET
    )

    def to_dict(self) -> dict[str, Any]:
        name: None | str | Unset
        if isinstance(self.name, Unset):
            name = UNSET
        else:
            name = self.name

        s3_output_bucket: None | str | Unset
        if isinstance(self.s3_output_bucket, Unset):
            s3_output_bucket = UNSET
        else:
            s3_output_bucket = self.s3_output_bucket

        s3_output_prefix: None | str | Unset
        if isinstance(self.s3_output_prefix, Unset):
            s3_output_prefix = UNSET
        else:
            s3_output_prefix = self.s3_output_prefix

        s3_input_prefix: None | str | Unset
        if isinstance(self.s3_input_prefix, Unset):
            s3_input_prefix = UNSET
        else:
            s3_input_prefix = self.s3_input_prefix

        s3_assume_role_arn: None | str | Unset
        if isinstance(self.s3_assume_role_arn, Unset):
            s3_assume_role_arn = UNSET
        else:
            s3_assume_role_arn = self.s3_assume_role_arn

        polling_enabled: bool | None | Unset
        if isinstance(self.polling_enabled, Unset):
            polling_enabled = UNSET
        else:
            polling_enabled = self.polling_enabled

        notifications_enabled: bool | None | Unset
        if isinstance(self.notifications_enabled, Unset):
            notifications_enabled = UNSET
        else:
            notifications_enabled = self.notifications_enabled

        flag_threshold: float | None | Unset
        if isinstance(self.flag_threshold, Unset):
            flag_threshold = UNSET
        else:
            flag_threshold = self.flag_threshold

        slack_webhook_url: None | str | Unset
        if isinstance(self.slack_webhook_url, Unset):
            slack_webhook_url = UNSET
        else:
            slack_webhook_url = self.slack_webhook_url

        session_content_retention_days: int | None | Unset
        if isinstance(self.session_content_retention_days, Unset):
            session_content_retention_days = UNSET
        else:
            session_content_retention_days = self.session_content_retention_days

        settings_distribution: None | str | Unset
        if isinstance(self.settings_distribution, Unset):
            settings_distribution = UNSET
        elif isinstance(
            self.settings_distribution, OrgSettingsUpdateSettingsDistributionType0
        ):
            settings_distribution = self.settings_distribution.value
        else:
            settings_distribution = self.settings_distribution

        field_dict: dict[str, Any] = {}

        field_dict.update({})
        if name is not UNSET:
            field_dict["name"] = name
        if s3_output_bucket is not UNSET:
            field_dict["s3_output_bucket"] = s3_output_bucket
        if s3_output_prefix is not UNSET:
            field_dict["s3_output_prefix"] = s3_output_prefix
        if s3_input_prefix is not UNSET:
            field_dict["s3_input_prefix"] = s3_input_prefix
        if s3_assume_role_arn is not UNSET:
            field_dict["s3_assume_role_arn"] = s3_assume_role_arn
        if polling_enabled is not UNSET:
            field_dict["polling_enabled"] = polling_enabled
        if notifications_enabled is not UNSET:
            field_dict["notifications_enabled"] = notifications_enabled
        if flag_threshold is not UNSET:
            field_dict["flag_threshold"] = flag_threshold
        if slack_webhook_url is not UNSET:
            field_dict["slack_webhook_url"] = slack_webhook_url
        if session_content_retention_days is not UNSET:
            field_dict["session_content_retention_days"] = (
                session_content_retention_days
            )
        if settings_distribution is not UNSET:
            field_dict["settings_distribution"] = settings_distribution

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)

        def _parse_name(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        name = _parse_name(d.pop("name", UNSET))

        def _parse_s3_output_bucket(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        s3_output_bucket = _parse_s3_output_bucket(d.pop("s3_output_bucket", UNSET))

        def _parse_s3_output_prefix(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        s3_output_prefix = _parse_s3_output_prefix(d.pop("s3_output_prefix", UNSET))

        def _parse_s3_input_prefix(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        s3_input_prefix = _parse_s3_input_prefix(d.pop("s3_input_prefix", UNSET))

        def _parse_s3_assume_role_arn(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        s3_assume_role_arn = _parse_s3_assume_role_arn(
            d.pop("s3_assume_role_arn", UNSET)
        )

        def _parse_polling_enabled(data: object) -> bool | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(bool | None | Unset, data)

        polling_enabled = _parse_polling_enabled(d.pop("polling_enabled", UNSET))

        def _parse_notifications_enabled(data: object) -> bool | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(bool | None | Unset, data)

        notifications_enabled = _parse_notifications_enabled(
            d.pop("notifications_enabled", UNSET)
        )

        def _parse_flag_threshold(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        flag_threshold = _parse_flag_threshold(d.pop("flag_threshold", UNSET))

        def _parse_slack_webhook_url(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        slack_webhook_url = _parse_slack_webhook_url(d.pop("slack_webhook_url", UNSET))

        def _parse_session_content_retention_days(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        session_content_retention_days = _parse_session_content_retention_days(
            d.pop("session_content_retention_days", UNSET)
        )

        def _parse_settings_distribution(
            data: object,
        ) -> None | OrgSettingsUpdateSettingsDistributionType0 | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                settings_distribution_type_0 = (
                    OrgSettingsUpdateSettingsDistributionType0(data)
                )

                return settings_distribution_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | OrgSettingsUpdateSettingsDistributionType0 | Unset, data)

        settings_distribution = _parse_settings_distribution(
            d.pop("settings_distribution", UNSET)
        )

        org_settings_update = cls(
            name=name,
            s3_output_bucket=s3_output_bucket,
            s3_output_prefix=s3_output_prefix,
            s3_input_prefix=s3_input_prefix,
            s3_assume_role_arn=s3_assume_role_arn,
            polling_enabled=polling_enabled,
            notifications_enabled=notifications_enabled,
            flag_threshold=flag_threshold,
            slack_webhook_url=slack_webhook_url,
            session_content_retention_days=session_content_retention_days,
            settings_distribution=settings_distribution,
        )

        return org_settings_update
