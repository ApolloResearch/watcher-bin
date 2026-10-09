from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.org_settings_settings_distribution import OrgSettingsSettingsDistribution
from ..models.org_settings_slack_alert_detail import OrgSettingsSlackAlertDetail
from ..types import UNSET, Unset

T = TypeVar("T", bound="OrgSettings")


@_attrs_define
class OrgSettings:
    """Response from GET /v1/org/settings.

    The Slack webhook URL is write-only: responses expose only the
    `slack_webhook_configured` flag and `slack_webhook_hint` (the URL's
    last 4 characters, for confirming which webhook is set), never the
    full URL.

    `slack_webhook_managed` is True when the deployment supplies the webhook
    URL through the `SLACK_WEBHOOK_URL` environment variable. That value takes
    precedence over anything stored per organization, so the configured flag
    and hint then describe the deployment's URL, and the settings API refuses
    writes to `slack_webhook_url`.

        Attributes:
            organization_id (str):
            name (str):
            settings_distribution (OrgSettingsSettingsDistribution):
            restrict_cross_user_session_content (bool):
            s3_output_bucket (None | str | Unset):
            s3_output_prefix (str | Unset):  Default: 'flagged-sessions/'.
            s3_input_prefix (str | Unset):  Default: ''.
            s3_assume_role_arn (None | str | Unset):
            polling_enabled (bool | Unset):  Default: True.
            notifications_enabled (bool | Unset):  Default: False.
            flag_threshold (float | Unset):  Default: 7.0.
            slack_webhook_configured (bool | Unset):  Default: False.
            slack_webhook_hint (None | str | Unset):
            slack_webhook_managed (bool | Unset):  Default: False.
            slack_alert_detail (OrgSettingsSlackAlertDetail | Unset): Slack alert detail level. Findings-only alerts include
                findings and aggregates, excluding session content. Default: OrgSettingsSlackAlertDetail.FULL.
            session_content_retention_days (int | None | Unset):
    """

    organization_id: str
    name: str
    settings_distribution: OrgSettingsSettingsDistribution
    restrict_cross_user_session_content: bool
    s3_output_bucket: None | str | Unset = UNSET
    s3_output_prefix: str | Unset = "flagged-sessions/"
    s3_input_prefix: str | Unset = ""
    s3_assume_role_arn: None | str | Unset = UNSET
    polling_enabled: bool | Unset = True
    notifications_enabled: bool | Unset = False
    flag_threshold: float | Unset = 7.0
    slack_webhook_configured: bool | Unset = False
    slack_webhook_hint: None | str | Unset = UNSET
    slack_webhook_managed: bool | Unset = False
    slack_alert_detail: OrgSettingsSlackAlertDetail | Unset = (
        OrgSettingsSlackAlertDetail.FULL
    )
    session_content_retention_days: int | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        organization_id = self.organization_id

        name = self.name

        settings_distribution = self.settings_distribution.value

        restrict_cross_user_session_content = self.restrict_cross_user_session_content

        s3_output_bucket: None | str | Unset
        if isinstance(self.s3_output_bucket, Unset):
            s3_output_bucket = UNSET
        else:
            s3_output_bucket = self.s3_output_bucket

        s3_output_prefix = self.s3_output_prefix

        s3_input_prefix = self.s3_input_prefix

        s3_assume_role_arn: None | str | Unset
        if isinstance(self.s3_assume_role_arn, Unset):
            s3_assume_role_arn = UNSET
        else:
            s3_assume_role_arn = self.s3_assume_role_arn

        polling_enabled = self.polling_enabled

        notifications_enabled = self.notifications_enabled

        flag_threshold = self.flag_threshold

        slack_webhook_configured = self.slack_webhook_configured

        slack_webhook_hint: None | str | Unset
        if isinstance(self.slack_webhook_hint, Unset):
            slack_webhook_hint = UNSET
        else:
            slack_webhook_hint = self.slack_webhook_hint

        slack_webhook_managed = self.slack_webhook_managed

        slack_alert_detail: str | Unset = UNSET
        if not isinstance(self.slack_alert_detail, Unset):
            slack_alert_detail = self.slack_alert_detail.value

        session_content_retention_days: int | None | Unset
        if isinstance(self.session_content_retention_days, Unset):
            session_content_retention_days = UNSET
        else:
            session_content_retention_days = self.session_content_retention_days

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "organization_id": organization_id,
                "name": name,
                "settings_distribution": settings_distribution,
                "restrict_cross_user_session_content": restrict_cross_user_session_content,
            }
        )
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
        if slack_webhook_configured is not UNSET:
            field_dict["slack_webhook_configured"] = slack_webhook_configured
        if slack_webhook_hint is not UNSET:
            field_dict["slack_webhook_hint"] = slack_webhook_hint
        if slack_webhook_managed is not UNSET:
            field_dict["slack_webhook_managed"] = slack_webhook_managed
        if slack_alert_detail is not UNSET:
            field_dict["slack_alert_detail"] = slack_alert_detail
        if session_content_retention_days is not UNSET:
            field_dict["session_content_retention_days"] = (
                session_content_retention_days
            )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        organization_id = d.pop("organization_id")

        name = d.pop("name")

        settings_distribution = OrgSettingsSettingsDistribution(
            d.pop("settings_distribution")
        )

        restrict_cross_user_session_content = d.pop(
            "restrict_cross_user_session_content"
        )

        def _parse_s3_output_bucket(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        s3_output_bucket = _parse_s3_output_bucket(d.pop("s3_output_bucket", UNSET))

        s3_output_prefix = d.pop("s3_output_prefix", UNSET)

        s3_input_prefix = d.pop("s3_input_prefix", UNSET)

        def _parse_s3_assume_role_arn(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        s3_assume_role_arn = _parse_s3_assume_role_arn(
            d.pop("s3_assume_role_arn", UNSET)
        )

        polling_enabled = d.pop("polling_enabled", UNSET)

        notifications_enabled = d.pop("notifications_enabled", UNSET)

        flag_threshold = d.pop("flag_threshold", UNSET)

        slack_webhook_configured = d.pop("slack_webhook_configured", UNSET)

        def _parse_slack_webhook_hint(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        slack_webhook_hint = _parse_slack_webhook_hint(
            d.pop("slack_webhook_hint", UNSET)
        )

        slack_webhook_managed = d.pop("slack_webhook_managed", UNSET)

        _slack_alert_detail = d.pop("slack_alert_detail", UNSET)
        slack_alert_detail: OrgSettingsSlackAlertDetail | Unset
        if isinstance(_slack_alert_detail, Unset):
            slack_alert_detail = UNSET
        else:
            slack_alert_detail = OrgSettingsSlackAlertDetail(_slack_alert_detail)

        def _parse_session_content_retention_days(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        session_content_retention_days = _parse_session_content_retention_days(
            d.pop("session_content_retention_days", UNSET)
        )

        org_settings = cls(
            organization_id=organization_id,
            name=name,
            settings_distribution=settings_distribution,
            restrict_cross_user_session_content=restrict_cross_user_session_content,
            s3_output_bucket=s3_output_bucket,
            s3_output_prefix=s3_output_prefix,
            s3_input_prefix=s3_input_prefix,
            s3_assume_role_arn=s3_assume_role_arn,
            polling_enabled=polling_enabled,
            notifications_enabled=notifications_enabled,
            flag_threshold=flag_threshold,
            slack_webhook_configured=slack_webhook_configured,
            slack_webhook_hint=slack_webhook_hint,
            slack_webhook_managed=slack_webhook_managed,
            slack_alert_detail=slack_alert_detail,
            session_content_retention_days=session_content_retention_days,
        )

        org_settings.additional_properties = d
        return org_settings

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
