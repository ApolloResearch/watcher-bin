from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Self, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.hook_append_anchor import HookAppendAnchor
    from ..models.hook_call_error import HookCallError
    from ..models.pre_tool_use_hook_response import PreToolUseHookResponse


T = TypeVar("T", bound="HookAppendResponse")


@_attrs_define
class HookAppendResponse:
    """A committed append anchor and its ordered per-call results.

    Use ``append_after`` directly in the next append request; it identifies
    the last stored message from this request, not a tentative write or a
    server-selected latest branch. An empty delta echoes its input anchor.
    Messages and available decisions are recorded before this response. Stage
    grades that exceeded their wait deadline may still finish afterwards.
    ``results`` is always a list, including for scalar input, and is empty for
    transcript-only ingestion. Another writer can still advance the chain
    before the next request, which then uses the normal conflict recovery.

        Attributes:
            append_after (HookAppendAnchor): The exact stored message after which a delta begins.

                Ingest responses and successful hook appends return this session/trajectory
                pair for the next append. Keep both fields together: a session may contain
                several branches, and the server never guesses which leaf the caller observed.
                A later write can overtake the anchor; on an append conflict, reconcile with
                a full transcript upload before resuming deltas.
            results (list[HookCallError | PreToolUseHookResponse]):
    """

    append_after: HookAppendAnchor
    results: list[HookCallError | PreToolUseHookResponse]
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.pre_tool_use_hook_response import PreToolUseHookResponse

        append_after = self.append_after.to_dict()

        results = []
        for results_item_data in self.results:
            results_item: dict[str, Any]
            if isinstance(results_item_data, PreToolUseHookResponse):
                results_item = results_item_data.to_dict()
            else:
                results_item = results_item_data.to_dict()

            results.append(results_item)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "append_after": append_after,
                "results": results,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        from ..models.hook_append_anchor import HookAppendAnchor
        from ..models.hook_call_error import HookCallError
        from ..models.pre_tool_use_hook_response import PreToolUseHookResponse

        d = dict(src_dict)
        append_after = HookAppendAnchor.from_dict(d.pop("append_after"))

        results = []
        _results = d.pop("results")
        for results_item_data in _results:

            def _parse_results_item(
                data: object,
            ) -> HookCallError | PreToolUseHookResponse:
                try:
                    if not isinstance(data, dict):
                        raise TypeError()
                    results_item_type_0 = PreToolUseHookResponse.from_dict(data)

                    return results_item_type_0
                except (TypeError, ValueError, AttributeError, KeyError):
                    pass
                if not isinstance(data, dict):
                    raise TypeError()
                results_item_type_1 = HookCallError.from_dict(data)

                return results_item_type_1

            results_item = _parse_results_item(results_item_data)

            results.append(results_item)

        hook_append_response = cls(
            append_after=append_after,
            results=results,
        )

        hook_append_response.additional_properties = d
        return hook_append_response

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
