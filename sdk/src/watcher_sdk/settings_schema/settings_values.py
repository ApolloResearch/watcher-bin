"""Helpers for the ``{value, permission}`` wrapper form a setting node may take in YAML."""

from __future__ import annotations

from typing import Any

_SETTING_KEYS = {"value", "permission"}


def is_setting_value(value: object) -> bool:
    return isinstance(value, dict) and "value" in value and set(value).issubset(_SETTING_KEYS)


def unwrap_setting_value(value: Any) -> Any:
    if is_setting_value(value):
        return value["value"]
    return value
