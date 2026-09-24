"""Merge functions and the permission (locked/modifiable/additions_allowed) engine for settings trees."""

from __future__ import annotations

import fnmatch
from collections.abc import Callable, Mapping
from typing import Any

from pydantic import BaseModel

from watcher_sdk.settings_schema.settings_values import is_setting_value as _shared_is_setting_value
from watcher_sdk.settings_schema.settings_values import unwrap_setting_value
from watcher_sdk.settings_schema.watcher_settings_yaml_schema import (
    BoolSetting,
    IntSetting,
    Permission,
    StrSetting,
)

NO_DIFF = object()

# Reserved key inside ``tool_thresholds`` holding the pair for a tool nothing else covers —
# no entry of its own, no matching glob, and no builtin default. Named for the tools it
# applies to rather than its place in the chain, and deliberately not ``default``: that
# word already means the builtin per-tool table (``DEFAULT_TOOL_THRESHOLDS``).
# It lives in the collection so it inherits the collection's lock: a fallback settable from
# outside a locked table would auto-approve exactly the tools the lock exists to catch.
# Deliberately not a glob — ``*`` fans out over every matching entry at merge time (see
# ``_merge_profile_tool_thresholds``), which is what the Auto and Skip Permissions profiles
# are built on and the opposite of a fallback. Reserved the way ``permission`` already is,
# and skipped in the same places.
UNKNOWN_TOOL_THRESHOLD_KEY = "unknown"
RESERVED_TOOL_THRESHOLD_KEYS = frozenset({"permission", UNKNOWN_TOOL_THRESHOLD_KEY})


def is_tool_glob(tool_name: str) -> bool:
    return any(char in tool_name for char in "*?[")


def resolve_tool_pattern(
    entries: Mapping[str, Any],
    tool_name: str,
    is_matchable_entry: Callable[[Any], bool] | None = None,
) -> str | None:
    if tool_name in entries and _is_matchable(entries[tool_name], is_matchable_entry):
        return tool_name
    for pattern, value in reversed(list(entries.items())):
        if not is_tool_glob(pattern) or not _is_matchable(value, is_matchable_entry):
            continue
        if fnmatch.fnmatchcase(tool_name, pattern):
            return pattern
    return None


def _is_matchable(value: Any, is_matchable_entry: Callable[[Any], bool] | None) -> bool:
    return is_matchable_entry is None or is_matchable_entry(value)


def merge_admin(base: Any, overlay: Any) -> Any:
    return _merge_admin_value(base, overlay, ())


def _merge_admin_value(base: Any, overlay: Any, path: tuple[str, ...]) -> Any:
    if is_setting_value(overlay):
        return overlay
    if isinstance(base, dict) and isinstance(overlay, dict):
        if path == ("profiles",) and overlay.get("permission") == "locked":
            return dict(overlay)
        result = dict(base)
        for key, value in overlay.items():
            if key == "rules" and isinstance(result.get("rules"), list) and isinstance(value, list):
                result[key] = merge_rule_lists(
                    result["rules"],
                    value,
                    enforce_permissions=False,
                    collection_permission="modifiable",
                )
            else:
                result[key] = _merge_admin_value(result.get(key), value, (*path, str(key)))
        return result
    return overlay


def merge_profile_admin(base: Any, overlay: Any, permission_root: dict[str, Any]) -> Any:
    return _merge_profile_admin_value(base, overlay, permission_root, ())


def _merge_profile_admin_value(base: Any, overlay: Any, permission_root: dict[str, Any], path: tuple[str, ...]) -> Any:
    if path_permission(permission_root, path) == "locked":
        return base
    if is_setting_value(overlay):
        return overlay
    if isinstance(base, dict) and isinstance(overlay, dict):
        if path == ("tool_thresholds",):
            return _merge_profile_tool_thresholds(base, overlay, permission_root, path, _merge_profile_admin_value)
        result = dict(base)
        for key, value in overlay.items():
            if key == "permission":
                _merge_permission(result, value)
            elif key == "rules" and isinstance(result.get("rules"), list) and isinstance(value, list):
                result[key] = merge_profile_rule_lists(result["rules"], value, permission_root, (*path, key))
            else:
                result[key] = _merge_profile_admin_value(result.get(key), value, permission_root, (*path, str(key)))
        return result
    return overlay


def merge_profile_local(base: Any, overlay: Any) -> Any:
    return _merge_profile_local_value(base, overlay, ())


def _merge_profile_local_value(base: Any, overlay: Any, path: tuple[str, ...]) -> Any:
    permission = node_permission(base)
    if permission == "locked":
        return base
    if is_setting_value(overlay):
        if _is_composite(base):
            return _merge_profile_local_value(base, unwrap(overlay), path)
        if permission == "additions_allowed":
            return base
        return replace_preserving_permission(base, unwrap(overlay))
    if isinstance(base, dict) and isinstance(overlay, dict):
        if path == ("tool_thresholds",):
            return _merge_profile_tool_thresholds(base, overlay, base, path, _merge_profile_local_value)
        return _merge_local_mapping(base, overlay, path, permission, _merge_profile_local_value)
    return merge_local(base, overlay)


def _merge_local_mapping(
    base: dict[str, Any],
    overlay: dict[str, Any],
    path: tuple[str, ...],
    permission: Permission,
    merge_child: Callable[[Any, Any, tuple[str, ...]], Any],
) -> dict[str, Any]:
    if permission == "additions_allowed":
        result = dict(base)
        for key, value in overlay.items():
            if key == "permission":
                continue
            value = unwrap_composite_wrappers(value)
            if key == "rules" and isinstance(result.get("rules"), list) and isinstance(value, list):
                result[key] = merge_rule_lists(
                    result["rules"],
                    value,
                    enforce_permissions=True,
                    collection_permission=permission,
                )
                continue
            # A list under additions_allowed (e.g. agents.enabled) means the
            # overlay may extend it but not drop what the base set: keep every
            # base entry, then append any overlay entries not already present.
            if isinstance(result.get(key), list) and isinstance(value, list):
                existing = result[key]
                additions = [item for item in strip_permissions(value) if item not in existing]
                result[key] = [*existing, *additions]
                continue
            if key not in result:
                result[key] = strip_permissions(value)
        return result

    result = dict(base)
    for key, value in overlay.items():
        if key == "permission":
            continue
        value = unwrap_composite_wrappers(value)
        if key == "rules" and isinstance(result.get("rules"), list) and isinstance(value, list):
            result[key] = merge_rule_lists(
                result["rules"],
                value,
                enforce_permissions=True,
                collection_permission=permission,
            )
            continue
        result[key] = merge_child(result.get(key), value, (*path, str(key)))
    return result


def _merge_profile_tool_thresholds(
    base: dict[str, Any],
    overlay: dict[str, Any],
    permission_root: dict[str, Any],
    path: tuple[str, ...],
    merge_value: Callable[[Any, Any, dict[str, Any], tuple[str, ...]], Any]
    | Callable[[Any, Any, tuple[str, ...]], Any],
) -> dict[str, Any]:
    result = dict(base)
    glob_items: list[tuple[str, Any]] = []
    exact_items: list[tuple[str, Any]] = []
    for key, value in overlay.items():
        if key == "permission":
            _merge_permission(result, value)
        elif is_tool_glob(str(key)):
            glob_items.append((str(key), value))
        else:
            exact_items.append((str(key), value))

    for pattern, value in glob_items:
        _merge_profile_tool_threshold_entry(result, pattern, value, permission_root, path, merge_value)
        for tool_name in list(result):
            if (
                tool_name in RESERVED_TOOL_THRESHOLD_KEYS
                or is_tool_glob(tool_name)
                or not fnmatch.fnmatchcase(tool_name, pattern)
            ):
                continue
            _merge_profile_tool_threshold_entry(result, tool_name, value, permission_root, path, merge_value)

    for tool_name, value in exact_items:
        _merge_profile_tool_threshold_entry(result, tool_name, value, permission_root, path, merge_value)
    return result


def _merge_profile_tool_threshold_entry(
    result: dict[str, Any],
    tool_name: str,
    value: Any,
    permission_root: dict[str, Any],
    path: tuple[str, ...],
    merge_value: Callable[[Any, Any, dict[str, Any], tuple[str, ...]], Any]
    | Callable[[Any, Any, tuple[str, ...]], Any],
) -> None:
    if merge_value is _merge_profile_admin_value:
        result[tool_name] = _merge_profile_admin_value(
            result.get(tool_name), value, permission_root, (*path, tool_name)
        )
        return
    if node_permission(permission_root) == "additions_allowed" and tool_name in result:
        return
    result[tool_name] = _merge_profile_local_value(result.get(tool_name), value, (*path, tool_name))


def _merge_permission(result: dict[str, Any], value: Any) -> None:
    if value not in ("locked", "modifiable", "additions_allowed"):
        return
    result["permission"] = combine_permissions(node_permission(result), value)


def merge_local(base: Any, overlay: Any) -> Any:
    """Overlay a lesser principal's document (a machine's `settings.local.yaml`,
    a hook request's overrides) onto the admin-composed base, honouring the
    base's permissions.

    Permissions live on nodes *inside* the tree, so the merge must descend to
    see them: a `{value: ...}` wrapper around a mapping or list is treated as
    the mapping or list itself whatever the node's own permission (so an
    additions-allowed collection still takes wrapped additions), and a node
    that holds a locked (or additions-allowed) descendant is never replaced
    outright — a scalar or a
    whole new list over such a node keeps the base. Otherwise a wrapper or a
    scalar replaces the node, mappings merge key by key, `rules` lists merge
    by rule id and other lists are replaced. Silent pruning is deliberate for
    a machine's local file; `locked_override_paths` is the reporting
    twin for callers that must be told.
    """
    permission = node_permission(base)
    if permission == "locked":
        return base
    if is_setting_value(overlay):
        if _is_composite(base):
            return merge_local(base, unwrap(overlay))
        if permission == "additions_allowed":
            return base
        return replace_preserving_permission(base, unwrap(overlay))
    if isinstance(base, dict) and isinstance(overlay, dict):
        return _merge_local_mapping(base, overlay, (), permission, _merge_local_child)
    if isinstance(base, list) and isinstance(overlay, list):
        return list(overlay) if permission == "modifiable" and not _locked_descendants(base, ()) else base
    if permission == "additions_allowed" or _locked_descendants(base, ()):
        return base
    return replace_preserving_permission(base, overlay)


def _is_composite(node: Any) -> bool:
    """A mapping or list that is settings structure, not a `{value: ...}` leaf."""
    return isinstance(node, (dict, list)) and not is_setting_value(node)


def unwrap_composite_wrappers(node: Any) -> Any:
    """Strip `{value: ...}` wrappers around mappings and lists at every depth.

    The wrapper is the settings-value form for scalars; around structure it
    means the structure itself, so every gate that keys on a child's shape
    (`rules` lists and the items inside them, list extension under
    `additions_allowed`) sees what the caller meant rather than a one-key
    mapping. Scalar wrappers pass through unchanged. Applied to an overlay
    child before the local merges and the lock walker look at it, and to a
    whole overrides document before validation, so the shared merge entry
    points agree on one shape.
    """
    if is_setting_value(node):
        inner = node["value"]
        return unwrap_composite_wrappers(inner) if isinstance(inner, (dict, list)) else node
    if isinstance(node, dict):
        return {key: unwrap_composite_wrappers(value) for key, value in node.items()}
    if isinstance(node, list):
        return [unwrap_composite_wrappers(item) for item in node]
    return node


def _locked_descendants(node: Any, path: tuple[str, ...]) -> list[str]:
    """Dotted paths of every node strictly inside `node` that carries its own
    `locked` or `additions_allowed` permission — what replacing `node`
    outright would discard. Rules are named by id, other list items by index.
    """
    found: list[str] = []
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "permission":
                continue
            child_path = (*path, str(key))
            if node_permission(value) != "modifiable":
                found.append(".".join(child_path))
            else:
                found.extend(_locked_descendants(value, child_path))
    elif isinstance(node, list):
        for index, item in enumerate(node):
            label = item["id"] if isinstance(item, dict) and isinstance(item.get("id"), str) else str(index)
            item_path = (*path, label)
            if node_permission(item) != "modifiable":
                found.append(".".join(item_path))
            else:
                found.extend(_locked_descendants(item, item_path))
    return found


def _merge_local_child(base: Any, overlay: Any, path: tuple[str, ...]) -> Any:
    return merge_local(base, overlay)


def locked_override_paths(base: Any, overlay: Any, path: tuple[str, ...] = ()) -> list[str]:
    """Dotted paths where `merge_local` would silently keep the base.

    `merge_local` prunes a disallowed override without complaint — the right
    behaviour for a machine's stale `settings.local.yaml`, but a per-request
    override (the hook API's `settings_overrides`) must be *rejected*
    when it asks for something the admin locked, or the caller believes a
    policy is in force that is not. This walker mirrors `merge_local`'s
    permission gates exactly, reporting instead of pruning: every returned
    path is one the merge would drop. An empty result means the merge applies
    the whole overlay. Kept adjacent to the merge so the two evolve together.
    """
    dotted = ".".join(path) if path else "<root>"
    permission = node_permission(base)
    if permission == "locked":
        return [dotted]
    if is_setting_value(overlay):
        if _is_composite(base):
            return locked_override_paths(base, unwrap(overlay), path)
        if permission == "additions_allowed":
            return [dotted]
        return []
    if isinstance(base, dict) and isinstance(overlay, dict):
        violations: list[str] = []
        for key, value in overlay.items():
            if key == "permission":
                continue
            value = unwrap_composite_wrappers(value)
            child_path = (*path, str(key))
            if key == "rules" and isinstance(base.get("rules"), list) and isinstance(value, list):
                violations.extend(_locked_rule_overrides(base["rules"], value, permission, child_path))
            elif permission == "additions_allowed":
                # New keys are the allowed additions; lists extend in place.
                if isinstance(base.get(key), list) and isinstance(value, list):
                    continue
                if key in base:
                    violations.append(".".join(child_path))
            else:
                violations.extend(locked_override_paths(base.get(key), value, child_path))
        return violations
    if isinstance(base, list) and isinstance(overlay, list):
        return _locked_descendants(base, path) if permission == "modifiable" else [dotted]
    if permission == "additions_allowed":
        return [dotted]
    return _locked_descendants(base, path)


def _locked_rule_overrides(
    base_rules: list[Any],
    overlay_rules: list[Any],
    collection_permission: Permission,
    path: tuple[str, ...],
) -> list[str]:
    """The rule entries `merge_rule_lists` (permission-enforcing) would drop."""
    violations: list[str] = []
    by_id = {rule["id"]: rule for rule in base_rules if isinstance(rule, dict) and isinstance(rule.get("id"), str)}
    for overlay_rule in overlay_rules:
        if not isinstance(overlay_rule, dict) or not isinstance(overlay_rule.get("id"), str):
            continue
        rule_id = overlay_rule["id"]
        rule_path = ".".join((*path, rule_id))
        base_rule = by_id.get(rule_id)
        if base_rule is None:
            continue  # a new rule appends under any non-locked collection
        if collection_permission == "additions_allowed":
            violations.append(rule_path)
            continue
        rule_permission = node_permission(base_rule, collection_permission)
        if rule_permission in ("locked", "additions_allowed"):
            violations.append(rule_path)
            continue
        fields = {key: value for key, value in overlay_rule.items() if key != "id"}
        violations.extend(locked_override_paths(base_rule, fields, (*path, rule_id)))
    return violations


def merge_profile_rule_lists(
    base_rules: list[Any],
    overlay_rules: list[Any],
    permission_root: dict[str, Any],
    path: tuple[str, ...],
) -> list[Any]:
    result: list[Any] = [dict(rule) if isinstance(rule, dict) else rule for rule in base_rules]
    index = {
        rule["id"]: i for i, rule in enumerate(result) if isinstance(rule, dict) and isinstance(rule.get("id"), str)
    }
    for overlay_rule in overlay_rules:
        if not isinstance(overlay_rule, dict) or not isinstance(overlay_rule.get("id"), str):
            continue
        rule_id = overlay_rule["id"]
        if rule_id not in index:
            if path_permission(permission_root, path) == "locked":
                continue
            result.append(overlay_rule)
            index[rule_id] = len(result) - 1
            continue
        base_rule = result[index[rule_id]]
        if not isinstance(base_rule, dict):
            continue
        merged_rule = dict(base_rule)
        for key, value in overlay_rule.items():
            if key == "id":
                continue
            rule_path = (*path, rule_id, str(key))
            if path_permission(permission_root, rule_path) == "locked":
                continue
            merged_rule[key] = _merge_profile_admin_value(base_rule.get(key), value, permission_root, rule_path)
        result[index[rule_id]] = merged_rule
    return result


def merge_rule_lists(
    base_rules: list[Any],
    overlay_rules: list[Any],
    enforce_permissions: bool,
    collection_permission: Permission,
) -> list[Any]:
    result: list[Any] = [dict(rule) if isinstance(rule, dict) else rule for rule in base_rules]
    index = {
        rule["id"]: i for i, rule in enumerate(result) if isinstance(rule, dict) and isinstance(rule.get("id"), str)
    }
    for overlay_rule in overlay_rules:
        if not isinstance(overlay_rule, dict) or not isinstance(overlay_rule.get("id"), str):
            continue
        rule_id = overlay_rule["id"]
        if rule_id not in index:
            if enforce_permissions and collection_permission == "locked":
                continue
            result.append(strip_permissions(overlay_rule) if enforce_permissions else overlay_rule)
            index[rule_id] = len(result) - 1
            continue
        base_rule = result[index[rule_id]]
        if not isinstance(base_rule, dict):
            continue
        if enforce_permissions and collection_permission == "additions_allowed":
            continue
        rule_permission = node_permission(base_rule, collection_permission)
        if enforce_permissions and rule_permission in ("locked", "additions_allowed"):
            continue
        merged = merge_local(base_rule, overlay_rule) if enforce_permissions else merge_admin(base_rule, overlay_rule)
        result[index[rule_id]] = merged
    return result


def diff_against_base(base: Any, candidate: Any) -> Any:
    if node_permission(base) == "locked":
        return NO_DIFF
    if is_setting_value(candidate):
        candidate_value = unwrap(candidate)
        base_value = unwrap(base)
        if candidate_value == base_value:
            return NO_DIFF
        return candidate_value
    if isinstance(candidate, dict):
        result: dict[str, Any] = {}
        for key, value in candidate.items():
            if key in ("version", "permission"):
                continue
            base_value = base.get(key) if isinstance(base, dict) else None
            permission = node_permission(base_value)
            if permission == "locked":
                continue
            diff = diff_against_base(base_value, value)
            if diff is not NO_DIFF:
                result[key] = diff
        return result if result else NO_DIFF
    if isinstance(candidate, list):
        candidate_value = strip_permissions(candidate)
        base_value = strip_permissions(base)
        if candidate_value == base_value:
            return NO_DIFF
        if is_rule_list(base) and is_rule_list(candidate):
            return diff_rule_list(base, candidate)
        return candidate_value
    candidate_value = strip_permissions(candidate)
    base_value = strip_permissions(base)
    if candidate_value == base_value:
        return NO_DIFF
    return candidate_value


def is_rule_list(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(item, dict) and isinstance(item.get("id"), str) for item in value)


def diff_rule_list(base_rules: list[Any], candidate_rules: list[Any]) -> Any:
    base_by_id = {rule["id"]: rule for rule in base_rules if isinstance(rule, dict) and isinstance(rule.get("id"), str)}
    result: list[Any] = []
    for candidate_rule in candidate_rules:
        if not isinstance(candidate_rule, dict) or not isinstance(candidate_rule.get("id"), str):
            result.append(strip_permissions(candidate_rule))
            continue
        base_rule = base_by_id.get(candidate_rule["id"])
        if base_rule is None:
            result.append(strip_permissions(candidate_rule))
            continue
        diff = diff_against_base(base_rule, candidate_rule)
        if diff is NO_DIFF:
            continue
        if isinstance(diff, dict):
            diff["id"] = candidate_rule["id"]
            result.append(diff)
        else:
            result.append({"id": candidate_rule["id"], "value": diff})
    return result if result else NO_DIFF


def drop_derived_local_settings(settings: dict[str, Any]) -> dict[str, Any]:
    command_rules = settings.get("command_rules")
    if not isinstance(command_rules, dict):
        return settings
    rules = command_rules.get("rules")
    if not isinstance(rules, list):
        return settings
    for rule in rules:
        if isinstance(rule, dict):
            rule.pop("ai_summary", None)
    return settings


def assert_modifiable(root: dict[str, Any], path: tuple[str, ...]) -> None:
    permission = path_permission(root, path)
    if permission != "modifiable":
        raise ValueError(f"{'.'.join(path)} is {permission} by admin settings")


def assert_collection_can_add(root: dict[str, Any], path: tuple[str, ...]) -> None:
    permission = path_permission(root, path)
    if permission not in ("modifiable", "additions_allowed"):
        raise ValueError(f"{'.'.join(path)} is {permission} by admin settings")


def collection_can_add(root: dict[str, Any], path: tuple[str, ...]) -> bool:
    return path_permission(root, path) in ("modifiable", "additions_allowed")


def path_permission(root: Any, path: tuple[str, ...]) -> Permission:
    node = root
    permission = combine_permissions("modifiable", node_permission(node))
    for part in path:
        if permission == "locked":
            return "locked"
        if isinstance(node, dict) and part in node:
            node = node[part]
            permission = combine_permissions(permission, node_permission(node, permission))
            continue
        if isinstance(node, dict) and "rules" in node and isinstance(node["rules"], list):
            found = find_rule_in_list(node["rules"], part)
            if found is not None:
                node = found
                permission = combine_permissions(permission, node_permission(node, permission))
                continue
        if isinstance(node, list):
            found = find_rule_in_list(node, part)
            if found is not None:
                node = found
                permission = combine_permissions(permission, node_permission(node, permission))
                continue
        return permission
    return permission


def combine_permissions(inherited: Permission, current: Permission) -> Permission:
    if inherited == "locked" or current == "locked":
        return "locked"
    if inherited == "additions_allowed" or current == "additions_allowed":
        return "additions_allowed"
    return current


def node_permission(node: Any, inherited: Permission = "modifiable") -> Permission:
    if isinstance(node, dict):
        permission = node.get("permission", inherited)
        if permission in ("locked", "modifiable", "additions_allowed"):
            return permission
    return inherited


def is_setting_value(value: object) -> bool:
    return _shared_is_setting_value(value)


def replace_preserving_permission(base: Any, value: Any) -> Any:
    if is_setting_value(base):
        result = {"value": value}
        if "permission" in base:
            result["permission"] = base["permission"]
        return result
    return value


def strip_permissions(value: Any) -> Any:
    if is_setting_value(value):
        return unwrap(value)
    if isinstance(value, dict):
        return {key: strip_permissions(item) for key, item in value.items() if key != "permission"}
    if isinstance(value, list):
        return [strip_permissions(item) for item in value]
    return value


def unwrap(value: Any) -> Any:
    if is_setting_value(value):
        return unwrap_setting_value(value)
    if isinstance(value, BaseModel) and hasattr(value, "value"):
        return getattr(value, "value")  # noqa: B009
    return value


def unwrap_int(value: IntSetting | None) -> int:
    unwrapped = unwrap(value)
    if not isinstance(unwrapped, int):
        raise TypeError(f"Expected int setting, got {type(unwrapped).__name__}")
    return unwrapped


def unwrap_bool(value: BoolSetting) -> bool:
    unwrapped = unwrap(value)
    if not isinstance(unwrapped, bool):
        raise TypeError(f"Expected bool setting, got {type(unwrapped).__name__}")
    return unwrapped


def unwrap_str(value: StrSetting) -> str:
    unwrapped = unwrap(value)
    if not isinstance(unwrapped, str):
        raise TypeError(f"Expected str setting, got {type(unwrapped).__name__}")
    return unwrapped


def get_path(root: Any, path: tuple[str, ...]) -> Any:
    node = root
    for part in path:
        if not isinstance(node, dict):
            raise KeyError(".".join(path))
        node = node[part]
    return node


def get_path_or_none(root: Any, path: tuple[str, ...]) -> Any | None:
    try:
        return get_path(root, path)
    except KeyError:
        return None


def set_path(root: dict[str, Any], path: tuple[str, ...], value: object) -> None:
    node = root
    for part in path[:-1]:
        child = node.get(part)
        if not isinstance(child, dict):
            child = {}
            node[part] = child
        node = child
    node[path[-1]] = value


def delete_path(root: dict[str, Any], path: tuple[str, ...]) -> None:
    """Remove the value at ``path``, doing nothing if any key along the way is absent.

    Inverse of ``set_path``; used by settings self-healing to drop a merged node that no
    longer exists in the builtin baseline (e.g. a field renamed or removed from the schema
    that still lingers in a user's on-disk config).
    """
    if not path:
        return
    node: Any = root
    for part in path[:-1]:
        if not isinstance(node, dict) or part not in node:
            return
        node = node[part]
    if isinstance(node, dict):
        node.pop(path[-1], None)


def remove_local_tool_threshold_field(local: dict[str, Any], tool_name: str, field: str) -> None:
    tool_thresholds = local.get("tool_thresholds")
    if not isinstance(tool_thresholds, dict):
        return
    tool_settings = tool_thresholds.get(tool_name)
    if not isinstance(tool_settings, dict):
        return
    tool_settings.pop(field, None)
    if not has_non_permission_entries(tool_settings):
        tool_thresholds.pop(tool_name, None)
    if not has_non_permission_entries(tool_thresholds):
        local.pop("tool_thresholds", None)


def has_non_permission_entries(settings: dict[str, Any]) -> bool:
    return any(key != "permission" for key in settings)


def ensure_local_rules(local: dict[str, Any]) -> list[dict[str, Any]]:
    command_rules = local.setdefault("command_rules", {})
    if not isinstance(command_rules, dict):
        raise ValueError("command_rules in local settings must be a mapping")
    rules = command_rules.setdefault("rules", [])
    if not isinstance(rules, list):
        raise ValueError("command_rules.rules in local settings must be a list")
    return rules


def ensure_local_rule(local: dict[str, Any], rule_id: str) -> dict[str, Any]:
    rules = ensure_local_rules(local)
    for rule in rules:
        if isinstance(rule, dict) and rule.get("id") == rule_id:
            return rule
    rule = {"id": rule_id}
    rules.append(rule)
    return rule


def find_rule_raw(root: dict[str, Any], rule_id: str) -> dict[str, Any] | None:
    rules = get_path_or_none(root, ("command_rules", "rules"))
    if isinstance(rules, list):
        return find_rule_in_list(rules, rule_id)
    return None


def find_rule_in_list(rules: list[Any], rule_id: str) -> dict[str, Any] | None:
    for rule in rules:
        if isinstance(rule, dict) and rule.get("id") == rule_id:
            return rule
    return None
