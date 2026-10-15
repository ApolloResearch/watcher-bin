from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from typing_extensions import Self

from ..types import UNSET, Unset

T = TypeVar("T", bound="CodexGitInfo")


@_attrs_define
class CodexGitInfo:
    """Git info from a session_meta payload. Empty when the cwd isn't a git checkout.

    Attributes:
        commit_hash (None | str | Unset):
        branch (None | str | Unset):
        repository_url (None | str | Unset):
    """

    commit_hash: None | str | Unset = UNSET
    branch: None | str | Unset = UNSET
    repository_url: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        commit_hash: None | str | Unset
        if isinstance(self.commit_hash, Unset):
            commit_hash = UNSET
        else:
            commit_hash = self.commit_hash

        branch: None | str | Unset
        if isinstance(self.branch, Unset):
            branch = UNSET
        else:
            branch = self.branch

        repository_url: None | str | Unset
        if isinstance(self.repository_url, Unset):
            repository_url = UNSET
        else:
            repository_url = self.repository_url

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if commit_hash is not UNSET:
            field_dict["commit_hash"] = commit_hash
        if branch is not UNSET:
            field_dict["branch"] = branch
        if repository_url is not UNSET:
            field_dict["repository_url"] = repository_url

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        d = dict(src_dict)

        def _parse_commit_hash(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        commit_hash = _parse_commit_hash(d.pop("commit_hash", UNSET))

        def _parse_branch(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        branch = _parse_branch(d.pop("branch", UNSET))

        def _parse_repository_url(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        repository_url = _parse_repository_url(d.pop("repository_url", UNSET))

        codex_git_info = cls(
            commit_hash=commit_hash,
            branch=branch,
            repository_url=repository_url,
        )

        codex_git_info.additional_properties = d
        return codex_git_info

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
