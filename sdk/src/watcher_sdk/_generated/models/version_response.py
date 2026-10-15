from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from typing_extensions import Self

T = TypeVar("T", bound="VersionResponse")


@_attrs_define
class VersionResponse:
    """Response from GET /v1/version - the build stamped into this deployment.

    The build stamp deliberately excludes a timestamp: it must be a pure
    function of the tagged commit so identical release inputs produce
    identical, reproducible artifacts.

        Attributes:
            version (str):
            git_sha (None | str):
    """

    version: str
    git_sha: None | str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        version = self.version

        git_sha: None | str
        git_sha = self.git_sha

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "version": version,
                "git_sha": git_sha,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        d = dict(src_dict)
        version = d.pop("version")

        def _parse_git_sha(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        git_sha = _parse_git_sha(d.pop("git_sha"))

        version_response = cls(
            version=version,
            git_sha=git_sha,
        )

        version_response.additional_properties = d
        return version_response

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
