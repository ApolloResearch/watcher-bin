from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Self, TypeVar, cast
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.monitor_info_role import MonitorInfoRole
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.model_token_budget import ModelTokenBudget
    from ..models.monitor_context_policy import MonitorContextPolicy


T = TypeVar("T", bound="MonitorInfo")


@_attrs_define
class MonitorInfo:
    """One server-managed monitor as served by GET /v1/monitors.

    A monitor's prompt, model, and reasoning are server-owned and not part of
    its public description. What a client needs is here: ``context_policy``
    says what of the transcript to assemble, and ``token_budget`` carries the
    sizing facts for truncation (in place of a model name). Both are null for
    the server-invoked roles (``summarize``, ``deep_review``), which assemble
    their own context. ``grader_id`` names the row the monitor's grades carry
    as provenance.

        Attributes:
            role (MonitorInfoRole):
            name (str):
            description (str):
            client_invocable (bool):
            grader_id (UUID):
            context_policy (MonitorContextPolicy | None | Unset):
            token_budget (ModelTokenBudget | None | Unset):
    """

    role: MonitorInfoRole
    name: str
    description: str
    client_invocable: bool
    grader_id: UUID
    context_policy: MonitorContextPolicy | None | Unset = UNSET
    token_budget: ModelTokenBudget | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.model_token_budget import ModelTokenBudget
        from ..models.monitor_context_policy import MonitorContextPolicy

        role = self.role.value

        name = self.name

        description = self.description

        client_invocable = self.client_invocable

        grader_id = str(self.grader_id)

        context_policy: dict[str, Any] | None | Unset
        if isinstance(self.context_policy, Unset):
            context_policy = UNSET
        elif isinstance(self.context_policy, MonitorContextPolicy):
            context_policy = self.context_policy.to_dict()
        else:
            context_policy = self.context_policy

        token_budget: dict[str, Any] | None | Unset
        if isinstance(self.token_budget, Unset):
            token_budget = UNSET
        elif isinstance(self.token_budget, ModelTokenBudget):
            token_budget = self.token_budget.to_dict()
        else:
            token_budget = self.token_budget

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "role": role,
                "name": name,
                "description": description,
                "client_invocable": client_invocable,
                "grader_id": grader_id,
            }
        )
        if context_policy is not UNSET:
            field_dict["context_policy"] = context_policy
        if token_budget is not UNSET:
            field_dict["token_budget"] = token_budget

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        from ..models.model_token_budget import ModelTokenBudget
        from ..models.monitor_context_policy import MonitorContextPolicy

        d = dict(src_dict)
        role = MonitorInfoRole(d.pop("role"))

        name = d.pop("name")

        description = d.pop("description")

        client_invocable = d.pop("client_invocable")

        grader_id = UUID(d.pop("grader_id"))

        def _parse_context_policy(data: object) -> MonitorContextPolicy | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                context_policy_type_0 = MonitorContextPolicy.from_dict(data)

                return context_policy_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(MonitorContextPolicy | None | Unset, data)

        context_policy = _parse_context_policy(d.pop("context_policy", UNSET))

        def _parse_token_budget(data: object) -> ModelTokenBudget | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                token_budget_type_0 = ModelTokenBudget.from_dict(data)

                return token_budget_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(ModelTokenBudget | None | Unset, data)

        token_budget = _parse_token_budget(d.pop("token_budget", UNSET))

        monitor_info = cls(
            role=role,
            name=name,
            description=description,
            client_invocable=client_invocable,
            grader_id=grader_id,
            context_policy=context_policy,
            token_budget=token_budget,
        )

        monitor_info.additional_properties = d
        return monitor_info

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
