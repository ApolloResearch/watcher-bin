"""Validation, sanitization, and self-healing repair for merged Watcher settings trees."""

from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from watcher_sdk.settings_schema.watcher_settings_yaml_helpers import (
    NO_DIFF,
    delete_path,
    get_path,
    get_path_or_none,
    set_path,
    unwrap,
)
from watcher_sdk.settings_schema.watcher_settings_yaml_schema import SettingsLoadIssue, SettingsSource, WatcherSettings

# Upper bound on self-healing passes over an invalid merged settings tree. Each pass reverts
# at least one not-yet-handled node, and the tree has finitely many nodes, so repair always
# terminates; this constant is just a safety net against an unexpected non-converging case.
_MAX_REPAIR_PASSES = 100


def sanitize_overlay(
    base: dict[str, Any],
    overlay: dict[str, Any],
    source: SettingsSource,
    source_path: Path,
    issues: list[SettingsLoadIssue],
    merge: Callable[[Any, Any], Any],
) -> dict[str, Any]:
    if not overlay:
        return {}
    sanitized = _sanitize_overlay_value(base, overlay, source, source_path, issues, merge, ())
    return sanitized if isinstance(sanitized, dict) else {}


def _sanitize_overlay_value(
    base: dict[str, Any],
    value: Any,
    source: SettingsSource,
    source_path: Path,
    issues: list[SettingsLoadIssue],
    merge: Callable[[Any, Any], Any],
    path: tuple[str, ...],
) -> Any:
    if path == ("command_rules", "rules") and isinstance(value, list):
        return _sanitize_command_rule_list(base, value, source, source_path, issues, merge, path)
    validation_error = candidate_validation_error_at_path(base, value, merge, path)
    if validation_error is None:
        return value
    base_value = get_path_or_none(base, path)
    if isinstance(base_value, list):
        add_settings_load_issue(issues, source, source_path, path, validation_error)
        return NO_DIFF
    if looks_like_setting_value(value):
        return _sanitize_setting_value(base, value, source, source_path, issues, merge, path, validation_error)
    if isinstance(value, dict):
        return _sanitize_overlay_mapping(base, value, source, source_path, issues, merge, path)
    if isinstance(value, list):
        add_settings_load_issue(issues, source, source_path, path, validation_error)
        return NO_DIFF
    add_settings_load_issue(issues, source, source_path, path, validation_error)
    return NO_DIFF


def _sanitize_setting_value(
    base: dict[str, Any],
    value: dict[str, Any],
    source: SettingsSource,
    source_path: Path,
    issues: list[SettingsLoadIssue],
    merge: Callable[[Any, Any], Any],
    path: tuple[str, ...],
    validation_error: str,
) -> Any:
    sanitized: dict[str, Any] = {}
    if "value" in value:
        value_error = candidate_validation_error_at_path(base, value["value"], merge, path)
        if value_error is None:
            sanitized["value"] = value["value"]
        else:
            add_settings_load_issue(issues, source, source_path, (*path, "value"), value_error)
    if "permission" in value:
        sanitized["permission"] = value["permission"]
    if "value" not in sanitized and "permission" in sanitized:
        base_value = get_path_or_none(base, path)
        if base_value is not None:
            sanitized["value"] = unwrap(base_value)
    if sanitized and candidate_validation_error_at_path(base, sanitized, merge, path) is None:
        return sanitized
    if "permission" in sanitized:
        without_permission = dict(sanitized)
        without_permission.pop("permission", None)
        if without_permission and candidate_validation_error_at_path(base, without_permission, merge, path) is None:
            add_settings_load_issue(issues, source, source_path, (*path, "permission"), validation_error)
            return without_permission
    if "value" not in value:
        add_settings_load_issue(issues, source, source_path, path, validation_error)
    return NO_DIFF


def _sanitize_overlay_mapping(
    base: dict[str, Any],
    value: dict[str, Any],
    source: SettingsSource,
    source_path: Path,
    issues: list[SettingsLoadIssue],
    merge: Callable[[Any, Any], Any],
    path: tuple[str, ...],
) -> Any:
    sanitized: dict[str, Any] = {}
    for key, item in value.items():
        child = _sanitize_overlay_value(base, item, source, source_path, issues, merge, (*path, str(key)))
        if child is not NO_DIFF:
            sanitized[key] = child
    if sanitized and candidate_validation_error_at_path(base, sanitized, merge, path) is None:
        return sanitized
    return NO_DIFF


def _sanitize_command_rule_list(
    base: dict[str, Any],
    rules: list[Any],
    source: SettingsSource,
    source_path: Path,
    issues: list[SettingsLoadIssue],
    merge: Callable[[Any, Any], Any],
    path: tuple[str, ...],
) -> Any:
    sanitized: list[dict[str, Any]] = []
    for index, rule in enumerate(rules):
        sanitized_rule = _sanitize_command_rule(base, rule, source, source_path, issues, merge, path, index)
        if sanitized_rule is not None:
            sanitized.append(sanitized_rule)
    if sanitized and candidate_validation_error_at_path(base, sanitized, merge, path) is None:
        return sanitized
    return NO_DIFF


def _sanitize_command_rule(
    base: dict[str, Any],
    rule: Any,
    source: SettingsSource,
    source_path: Path,
    issues: list[SettingsLoadIssue],
    merge: Callable[[Any, Any], Any],
    path: tuple[str, ...],
    index: int,
) -> dict[str, Any] | None:
    if not isinstance(rule, dict):
        add_settings_load_issue(
            issues,
            source,
            source_path,
            f"{format_setting_path(path)}[{index}]",
            "Rule must be a mapping",
        )
        return None
    rule_id = rule.get("id")
    if not isinstance(rule_id, str):
        add_settings_load_issue(
            issues,
            source,
            source_path,
            f"{format_setting_path(path)}[{index}]",
            "Rule must have a string id",
        )
        return None
    validation_error = candidate_validation_error_at_path(base, [rule], merge, path)
    if validation_error is None:
        return rule
    sanitized: dict[str, Any] = {"id": rule_id}
    for key, value in rule.items():
        if key == "id":
            continue
        candidate = {"id": rule_id, key: value}
        field_error = candidate_validation_error_at_path(base, [candidate], merge, path)
        if field_error is None:
            sanitized[key] = value
        else:
            add_settings_load_issue(
                issues,
                source,
                source_path,
                f"{format_setting_path(path)}[{rule_id}].{key}",
                field_error,
            )
    if len(sanitized) > 1 and candidate_validation_error_at_path(base, [sanitized], merge, path) is None:
        return sanitized
    add_settings_load_issue(issues, source, source_path, f"{format_setting_path(path)}[{rule_id}]", validation_error)
    return None


def candidate_validation_error_at_path(
    base: dict[str, Any],
    value: Any,
    merge: Callable[[Any, Any], Any],
    path: tuple[str, ...],
) -> str | None:
    overlay = value if not path else overlay_at_path(path, value)
    return candidate_validation_error(base, overlay, merge)


def candidate_validation_error(
    base: dict[str, Any],
    overlay: Any,
    merge: Callable[[Any, Any], Any],
) -> str | None:
    try:
        WatcherSettings.model_validate(merge(base, overlay))
    except ValidationError as e:
        return validation_error_summary(e)
    return None


def overlay_at_path(path: tuple[str, ...], value: Any) -> dict[str, Any]:
    overlay: Any = value
    for part in reversed(path):
        overlay = {part: overlay}
    return overlay


def looks_like_setting_value(value: Any) -> bool:
    return isinstance(value, dict) and bool(value) and set(value).issubset({"value", "permission"})


def validate_settings_tree(settings: dict[str, Any], description: str) -> None:
    try:
        WatcherSettings.model_validate(settings)
    except ValidationError as e:
        raise ValueError(f"{description} are invalid: {validation_error_summary(e)}") from e


def repair_settings_tree(
    candidate: dict[str, Any],
    fallback: dict[str, Any],
    source: SettingsSource,
    source_path: Path,
    issues: list[SettingsLoadIssue],
) -> dict[str, Any]:
    """Return a guaranteed-valid version of ``candidate``, healing invalid nodes in place of crashing.

    The merge pipeline can produce an effective settings tree that no single on-disk layer
    would, because a value that is valid on its own becomes invalid once another layer is laid
    on top of it (for example, a user who set ``deny_threshold: 8`` combined with the builtin
    ``permissive`` profile, which raises ``flag_threshold`` to 8, yields ``flag == deny``, which
    the schema rejects). Hard-validating that merged tree would stop Watcher from starting, so
    instead we repair it.

    For every Pydantic validation error we locate the deepest real node in ``candidate`` that the
    error points at (skipping the synthetic union/type markers Pydantic appends to the location),
    then either reset that node to the corresponding value in ``fallback`` (a known-valid tree) or,
    if the node does not exist in ``fallback`` at all (a removed or renamed setting that lingers in
    the user's config), drop it. Each repair is recorded as a :class:`SettingsLoadIssue` so the UI
    and ``get_settings_load_errors`` can show the user what was changed and why. We re-validate and
    repeat until the tree is valid.

    The caller passes the admin baseline (builtin defaults plus any admin overrides) as
    ``fallback``, not the bare builtin. That way an invalid merged node reverts to what the admin
    pushed, including admin-locked values, instead of silently relaxing back to the shipped
    default; only the local or profile contribution that broke the merge is discarded. With no
    admin config the admin baseline is identical to the builtin defaults.

    Args:
        candidate: The fully merged settings tree to validate and, if needed, heal. Not mutated.
        fallback: A tree already known to be valid (the admin baseline) used as the source of
            replacement values and as the wholesale last resort.
        source: Which on-disk layer to attribute repairs to in the surfaced issue (the user's
            local config is the usual culprit and the most actionable for them to fix).
        source_path: Path of that layer, shown alongside the issue.
        issues: Accumulator the caller already threads through the load; repairs are appended here.

    Returns:
        A valid settings tree: ``candidate`` unchanged if it already validated, otherwise a healed
        copy. As an absolute last resort (nothing converged) a copy of ``fallback`` so that Watcher
        can always start.
    """
    try:
        WatcherSettings.model_validate(candidate)
        return candidate
    except ValidationError:
        pass

    repaired = deepcopy(candidate)
    handled_paths: set[tuple[str, ...]] = set()
    for _ in range(_MAX_REPAIR_PASSES):
        try:
            WatcherSettings.model_validate(repaired)
            return repaired
        except ValidationError as error:
            targets = _repair_targets(repaired, error)
        progressed = False
        for path, reason in targets:
            if not path or path in handled_paths:
                continue
            handled_paths.add(path)
            progressed = True
            _restore_or_drop(repaired, fallback, path, source, source_path, issues, reason)
        if not progressed:
            break

    add_settings_load_issue(
        issues,
        source,
        source_path,
        None,
        "Watcher settings could not be repaired and were reset to the administrator baseline "
        "(or Watcher's built-in defaults) so Watcher could start.",
    )
    return deepcopy(fallback)


def _repair_targets(candidate: dict[str, Any], error: ValidationError) -> list[tuple[tuple[str, ...], str]]:
    """Collapse a ValidationError into one (restore path, reason) per distinct node to repair."""
    targets: dict[tuple[str, ...], str] = {}
    for item in error.errors():
        path = _restore_path_for_loc(candidate, item.get("loc", ()))
        if path not in targets:
            targets[path] = item.get("msg", "Invalid value")
    return list(targets.items())


def _restore_path_for_loc(candidate: dict[str, Any], raw_location: object) -> tuple[str, ...]:
    """Find the deepest node in ``candidate`` that a Pydantic error location actually addresses.

    Pydantic appends synthetic parts to the location for union members and coerced scalar types
    (e.g. ``function-after[...]``, ``literal[...]``, ``int``, ``SettingWithPermission[...]``), and
    list errors carry integer indices. We keep only the leading run of string keys that exist in
    the tree, which is the largest subtree we can safely swap out wholesale.
    """
    if not isinstance(raw_location, tuple):
        return ()
    prefix: list[str] = []
    node: Any = candidate
    for part in raw_location:
        if not isinstance(part, str) or not isinstance(node, dict) or part not in node:
            break
        prefix.append(part)
        node = node[part]
    return tuple(prefix)


def _restore_or_drop(
    candidate: dict[str, Any],
    fallback: dict[str, Any],
    path: tuple[str, ...],
    source: SettingsSource,
    source_path: Path,
    issues: list[SettingsLoadIssue],
    reason: str,
) -> None:
    """Reset ``candidate`` at ``path`` to the builtin value, or drop it if the builtin has no such node."""
    try:
        fallback_value = get_path(fallback, path)
    except KeyError:
        delete_path(candidate, path)
        message = (
            f"This setting is not recognized after merging all settings layers ({reason}). "
            "It was ignored so Watcher could start; remove it from your settings file."
        )
        add_settings_load_issue(issues, source, source_path, path, message)
        return
    set_path(candidate, path, deepcopy(fallback_value))
    message = (
        f"This value was invalid after merging all settings layers ({reason}). "
        "It was reset to the administrator baseline (or Watcher's built-in default) so Watcher could start; "
        "update your settings file to keep a custom value."
    )
    add_settings_load_issue(issues, source, source_path, path, message)


def validation_error_summary(error: ValidationError) -> str:
    summaries: list[str] = []
    seen_locations: set[str] = set()
    for item in error.errors():
        loc = validation_error_location(item.get("loc", ()))
        if loc in seen_locations:
            continue
        seen_locations.add(loc)
        summaries.append(f"{loc}: {item.get('msg', 'Invalid value')}")
        if len(summaries) == 3:
            break
    return "; ".join(summaries) if summaries else str(error)


def validation_error_location(raw_location: object) -> str:
    if not isinstance(raw_location, tuple):
        return "<root>"
    # Pydantic inserts synthetic segments for the union branch and function
    # validators it tried, e.g. "function-after[validate_threshold_order(), ...]"
    # or "literal['locked','modifiable',...]". Those read as internal machinery,
    # not a path the author can act on. They always carry a "[", which a real
    # settings key never does, so dropping bracketed segments leaves the clean
    # dotted path (tool_thresholds.Bash.flag_threshold) an editor user expects.
    parts = [str(part) for part in raw_location if "[" not in str(part)]
    if parts and (parts[-1] in {"int", "float", "bool", "str", "list[str]"} or "SettingWithPermission" in parts[-1]):
        parts.pop()
    return ".".join(parts) if parts else "<root>"


def add_settings_load_issue(
    issues: list[SettingsLoadIssue],
    source: SettingsSource,
    source_path: Path,
    setting_path: tuple[str, ...] | str | None,
    message: str,
) -> None:
    formatted_path = format_setting_path(setting_path)
    if formatted_path and message.startswith(f"{formatted_path}: "):
        message = message.removeprefix(f"{formatted_path}: ")
    issues.append(
        SettingsLoadIssue(
            source=source,
            file_path=str(source_path),
            setting_path=formatted_path,
            message=message,
        )
    )


def format_settings_load_issue(issue: SettingsLoadIssue) -> str:
    source_label = "Admin" if issue.source == "admin" else "Local"
    setting = f" at {issue.setting_path}" if issue.setting_path else ""
    return f"{source_label} watcher settings ({issue.file_path}){setting}: {issue.message}"


def format_setting_path(setting_path: tuple[str, ...] | str | None) -> str | None:
    if setting_path is None:
        return None
    if isinstance(setting_path, str):
        return setting_path
    return ".".join(setting_path) if setting_path else None
