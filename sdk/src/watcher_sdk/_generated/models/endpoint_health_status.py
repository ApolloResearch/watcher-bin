from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Self, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.endpoint_health_agent import EndpointHealthAgent
    from ..models.endpoint_health_delivery import EndpointHealthDelivery
    from ..models.endpoint_health_snooze import EndpointHealthSnooze
    from ..models.endpoint_health_status_self_check_type_0 import (
        EndpointHealthStatusSelfCheckType0,
    )


T = TypeVar("T", bound="EndpointHealthStatus")


@_attrs_define
class EndpointHealthStatus:
    """Whether Watcher is fully on for the machine, as the client saw it at ``observed_at``.

    Only states, times and counts: never paths, folder or project names, snooze reasons, session IDs, settings
    contents or the self-check's text. A missing field means the client could not read it.

        Attributes:
            observed_at (datetime.datetime): When the client read these values, by the machine's clock.
            enforcement_mode (None | str | Unset): `enforce` (risky calls can be blocked), `observe` (graded, never blocked)
                or `paused` (nothing is evaluated, not even rules); null when the client could not read it.
            snooze (EndpointHealthSnooze | None | Unset): Whether grading is snoozed; null when the client could not read
                it.
            agents (list[EndpointHealthAgent] | None | Unset): Every coding agent Watcher has hooks for; null when the
                client could not read them.
            delivery (EndpointHealthDelivery | None | Unset): The upload backlog; null when the client could not read it.
            self_check (EndpointHealthStatusSelfCheckType0 | None | Unset): `watcher doctor` section name to `ok`, `warning`
                or `error`, for the sections the client checks in the background. A section is missing when its check failed to
                run; null when the client could not run the self-check at all.
            approval_bypass_sessions (int | None | Unset): How many open agent sessions run with an approval policy or
                sandbox that lets tool calls run without asking for approval, so Watcher records their calls but cannot grade or
                block them first: the sessions behind the `enforcement` self-check result. Null when the client could not check.
    """

    observed_at: datetime.datetime
    enforcement_mode: None | str | Unset = UNSET
    snooze: EndpointHealthSnooze | None | Unset = UNSET
    agents: list[EndpointHealthAgent] | None | Unset = UNSET
    delivery: EndpointHealthDelivery | None | Unset = UNSET
    self_check: EndpointHealthStatusSelfCheckType0 | None | Unset = UNSET
    approval_bypass_sessions: int | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.endpoint_health_delivery import EndpointHealthDelivery
        from ..models.endpoint_health_snooze import EndpointHealthSnooze
        from ..models.endpoint_health_status_self_check_type_0 import (
            EndpointHealthStatusSelfCheckType0,
        )

        observed_at = self.observed_at.isoformat()

        enforcement_mode: None | str | Unset
        if isinstance(self.enforcement_mode, Unset):
            enforcement_mode = UNSET
        else:
            enforcement_mode = self.enforcement_mode

        snooze: dict[str, Any] | None | Unset
        if isinstance(self.snooze, Unset):
            snooze = UNSET
        elif isinstance(self.snooze, EndpointHealthSnooze):
            snooze = self.snooze.to_dict()
        else:
            snooze = self.snooze

        agents: list[dict[str, Any]] | None | Unset
        if isinstance(self.agents, Unset):
            agents = UNSET
        elif isinstance(self.agents, list):
            agents = []
            for agents_type_0_item_data in self.agents:
                agents_type_0_item = agents_type_0_item_data.to_dict()
                agents.append(agents_type_0_item)

        else:
            agents = self.agents

        delivery: dict[str, Any] | None | Unset
        if isinstance(self.delivery, Unset):
            delivery = UNSET
        elif isinstance(self.delivery, EndpointHealthDelivery):
            delivery = self.delivery.to_dict()
        else:
            delivery = self.delivery

        self_check: dict[str, Any] | None | Unset
        if isinstance(self.self_check, Unset):
            self_check = UNSET
        elif isinstance(self.self_check, EndpointHealthStatusSelfCheckType0):
            self_check = self.self_check.to_dict()
        else:
            self_check = self.self_check

        approval_bypass_sessions: int | None | Unset
        if isinstance(self.approval_bypass_sessions, Unset):
            approval_bypass_sessions = UNSET
        else:
            approval_bypass_sessions = self.approval_bypass_sessions

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "observed_at": observed_at,
            }
        )
        if enforcement_mode is not UNSET:
            field_dict["enforcement_mode"] = enforcement_mode
        if snooze is not UNSET:
            field_dict["snooze"] = snooze
        if agents is not UNSET:
            field_dict["agents"] = agents
        if delivery is not UNSET:
            field_dict["delivery"] = delivery
        if self_check is not UNSET:
            field_dict["self_check"] = self_check
        if approval_bypass_sessions is not UNSET:
            field_dict["approval_bypass_sessions"] = approval_bypass_sessions

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        from ..models.endpoint_health_agent import EndpointHealthAgent
        from ..models.endpoint_health_delivery import EndpointHealthDelivery
        from ..models.endpoint_health_snooze import EndpointHealthSnooze
        from ..models.endpoint_health_status_self_check_type_0 import (
            EndpointHealthStatusSelfCheckType0,
        )

        d = dict(src_dict)
        observed_at = datetime.datetime.fromisoformat(d.pop("observed_at"))

        def _parse_enforcement_mode(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        enforcement_mode = _parse_enforcement_mode(d.pop("enforcement_mode", UNSET))

        def _parse_snooze(data: object) -> EndpointHealthSnooze | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                snooze_type_0 = EndpointHealthSnooze.from_dict(data)

                return snooze_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(EndpointHealthSnooze | None | Unset, data)

        snooze = _parse_snooze(d.pop("snooze", UNSET))

        def _parse_agents(data: object) -> list[EndpointHealthAgent] | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                agents_type_0 = []
                _agents_type_0 = data
                for agents_type_0_item_data in _agents_type_0:
                    agents_type_0_item = EndpointHealthAgent.from_dict(
                        agents_type_0_item_data
                    )

                    agents_type_0.append(agents_type_0_item)

                return agents_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(list[EndpointHealthAgent] | None | Unset, data)

        agents = _parse_agents(d.pop("agents", UNSET))

        def _parse_delivery(data: object) -> EndpointHealthDelivery | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                delivery_type_0 = EndpointHealthDelivery.from_dict(data)

                return delivery_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(EndpointHealthDelivery | None | Unset, data)

        delivery = _parse_delivery(d.pop("delivery", UNSET))

        def _parse_self_check(
            data: object,
        ) -> EndpointHealthStatusSelfCheckType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                self_check_type_0 = EndpointHealthStatusSelfCheckType0.from_dict(data)

                return self_check_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(EndpointHealthStatusSelfCheckType0 | None | Unset, data)

        self_check = _parse_self_check(d.pop("self_check", UNSET))

        def _parse_approval_bypass_sessions(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        approval_bypass_sessions = _parse_approval_bypass_sessions(
            d.pop("approval_bypass_sessions", UNSET)
        )

        endpoint_health_status = cls(
            observed_at=observed_at,
            enforcement_mode=enforcement_mode,
            snooze=snooze,
            agents=agents,
            delivery=delivery,
            self_check=self_check,
            approval_bypass_sessions=approval_bypass_sessions,
        )

        endpoint_health_status.additional_properties = d
        return endpoint_health_status

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
