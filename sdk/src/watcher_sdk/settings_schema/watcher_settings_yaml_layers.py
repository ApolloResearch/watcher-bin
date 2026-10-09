"""Settings layer assembly: builtin resource loading, YAML file parsing, and profile resolution."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable, Hashable
from functools import lru_cache
from importlib.resources import files
from pathlib import Path
from typing import Any, Literal, NamedTuple

import regex as regex_module
import yaml
from pydantic import ValidationError
from yaml import YAMLError
from yaml.constructor import ConstructorError
from yaml.nodes import MappingNode, Node

from watcher_sdk.settings_schema.watcher_settings_yaml_helpers import (
    NO_DIFF,
    diff_against_base,
    drop_derived_local_settings,
    get_path_or_none,
    is_rule_list,
    is_setting_value,
    locked_override_paths,
    merge_admin,
    merge_local,
    merge_profile_admin,
    merge_profile_local,
    node_permission,
    strip_permissions,
    unwrap,
    unwrap_composite_wrappers,
)
from watcher_sdk.settings_schema.watcher_settings_yaml_schema import (
    SettingsLoadIssue,
    SettingsSource,
    WatcherSettings,
)
from watcher_sdk.settings_schema.watcher_settings_yaml_validation import (
    add_settings_load_issue,
    command_rule_overlay_error,
    repair_settings_tree,
    sanitize_overlay,
    validate_settings_tree,
    validation_error_summary,
)

DEFAULT_PROFILE_ID = "default"
PROFILE_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]*$")

type LocalSettingsScope = Literal["none", "global", "all"]
type SettingsCacheKey = tuple[str, tuple[tuple[str, tuple[int, int] | None], ...]]


class AppliedOverlay(NamedTuple):
    """One layer above the administrator baseline, exactly as the effective merge applied it.

    ``base`` is the tree the layer merged onto, ``written`` the layer as its
    source holds it, ``overlay`` the layer after sanitizing against ``base``,
    and ``merge`` the function that merged them (with its permission root
    bound), so ``merge(base, overlay)`` reproduces the layer's step. Replaying
    the step with a stand-in overlay shows which paths the layer actually set:
    a path its permissions refused, or a value sanitizing pruned, never
    reaches the result. Sanitizing can also put the base's value in place of
    an invalid one it keeps the wrapper of, so ``written`` tells a value the
    source wrote from one sanitizing supplied.
    """

    base: dict[str, Any]
    written: dict[str, Any]
    overlay: dict[str, Any]
    merge: Callable[[Any, Any], Any]


_YAML_MERGE_KEY_TAG = "tag:yaml.org,2002:merge"
_YAML_MERGE_KEY = object()


class _UniqueKeySafeLoader(yaml.SafeLoader):
    """Safe YAML loader that rejects duplicate keys in every mapping."""

    def construct_mapping(self, node: Node, deep: bool = False) -> dict[Hashable, object]:
        if not isinstance(node, MappingNode):
            raise ConstructorError(None, None, "expected a mapping node", node.start_mark)
        keys: set[Hashable] = set()
        for key_node, _value_node in node.value:
            key_candidate: object = (
                _YAML_MERGE_KEY if key_node.tag == _YAML_MERGE_KEY_TAG else self.construct_object(key_node, deep=deep)
            )
            if not isinstance(key_candidate, Hashable):
                raise ConstructorError(
                    "while constructing a mapping",
                    node.start_mark,
                    "found unhashable mapping key",
                    key_node.start_mark,
                )
            if key_candidate in keys:
                raise ConstructorError(
                    "while constructing a mapping",
                    node.start_mark,
                    "found duplicate mapping key",
                    key_node.start_mark,
                )
            keys.add(key_candidate)
        return super().construct_mapping(node, deep=deep)


def load_settings_yaml(yaml_text: str) -> object:
    """Safely parse settings YAML while rejecting duplicate mapping keys."""
    return yaml.load(yaml_text, Loader=_UniqueKeySafeLoader)


class SettingsOverridesError(ValueError):
    """A per-request YAML or JSON settings overlay was rejected.

    Invalid documents and attempts to change admin-locked values raise this
    error. API handlers may forward `safe_detail` in a 422 response: it names
    setting paths and parser errors without including document contents.
    """

    @property
    def safe_detail(self) -> str:
        return self.args[0] if self.args else ""


def _reject_unprojectable_override_rules(data: dict[str, Any], merged: dict[str, Any]) -> None:
    """Refuse override-touched rules whose merged form the rule projection drops.

    A rule can carry a valid string `id` and pass whole-tree schema
    validation yet still be skipped by `command_rules_from_tree` — a new
    rule missing `category`, a non-string `regex`, a non-int `priority`
    — leaving the caller believing a rule is in force that never evaluates.
    A rule that projects but whose pattern does not compile is refused for
    the same reason: the evaluator treats an uncompilable pattern as "no
    match", so the rule would be accepted and never fire. Judged on the
    *merged* form so a partial update to an existing complete rule stays
    legal; a rule whose merged `decision` is `off` is a deliberate
    disable, not a projection failure.
    """
    from watcher_sdk.settings_schema.command_rules_eval import command_rules_from_tree

    rules = unwrap(get_path_or_none(data, ("command_rules", "rules")))
    if not isinstance(rules, list) or not rules:
        return
    touched = {rule["id"] for rule in rules if isinstance(rule, dict) and isinstance(rule.get("id"), str)}
    projected_rules = command_rules_from_tree(merged)
    projected = {rule.id for rule in projected_rules}
    for projected_rule in projected_rules:
        if projected_rule.id not in touched:
            continue
        try:
            # The evaluator's engine and flags (see command_rules_eval._valid_rules),
            # where an uncompilable active pattern suppresses every allow rule.
            regex_module.compile(projected_rule.pattern, regex_module.IGNORECASE)
        except regex_module.error as e:
            raise SettingsOverridesError(
                f"settings_overrides rule '{projected_rule.id}' has a regex that does not compile: {e}"
            ) from e
    merged_rules = unwrap(get_path_or_none(merged, ("command_rules", "rules")))
    if not isinstance(merged_rules, list):
        merged_rules = []
    for raw in merged_rules:
        if not isinstance(raw, dict):
            continue
        rule_id = raw.get("id")
        if not isinstance(rule_id, str) or rule_id not in touched or rule_id in projected:
            continue
        if unwrap(raw.get("decision", "triage")) == "off":
            continue
        raise SettingsOverridesError(
            f"settings_overrides rule '{rule_id}' does not form a complete active rule after merging "
            "(active rules need string tool_name/name/category/regex, an integer priority, and a known decision)"
        )


def _reject_unmergeable_override_rules(data: dict[str, Any]) -> None:
    """Refuse override rule entries the id-keyed rule merge would silently drop.

    `merge_rule_lists` skips any `command_rules.rules` item that is not a
    mapping carrying a string `id` — correct for a machine's local file,
    where boot must proceed, but a per-request override that loses a rule this
    way leaves the caller enforcing under a policy it merely believes is in
    force (the same reasoning as the locked-path rejection).
    """
    error = command_rule_overlay_error(data)
    if error is not None:
        raise SettingsOverridesError(f"settings_overrides {error}")


def merge_policy_settings(base: dict[str, Any], overlay: dict[str, Any] | None) -> dict[str, Any]:
    """Merge a stored policy while retaining malformed rules for conservative evaluation.

    ``base`` is the complete packaged settings tree. ``None`` means a stored
    document could not be read; an empty mapping is a valid empty overlay.
    The ordinary id-based merge drops malformed identities. Keeping those
    entries lets rule evaluation suppress approvals while preserving known
    restrictions, including after a caller reprojects the merged settings.
    """
    source = unwrap(overlay)
    if not isinstance(source, dict):
        source = {"command_rules": {"rules": None}}
    elif "command_rules" in source:
        # Only the rule group needs its `{value: ...}` wrappers removed. Removing
        # them everywhere would also drop `permission: locked` from wrapped lists
        # and mappings such as `aliases`, letting a per-request override replace
        # a value the admin locked.
        source = {**source, "command_rules": unwrap_composite_wrappers(source["command_rules"])}
    merged = merge_admin(base, source)
    if "command_rules" not in source:
        return merged
    source_group = source["command_rules"]
    if isinstance(source_group, dict) and "rules" not in source_group and "value" not in source_group:
        return merged
    source_rules = source_group["rules"] if isinstance(source_group, dict) and "rules" in source_group else source_group
    if isinstance(source_group, dict) and "rules" in source_group and isinstance(source_rules, list):
        dropped = [rule for rule in source_rules if not isinstance(rule, dict) or not isinstance(rule.get("id"), str)]
        if not dropped:
            return merged
        rules = [*merged["command_rules"]["rules"], *dropped]
    else:
        rules = [*base["command_rules"]["rules"], {"rules": source_rules}]
    merged_group = merged["command_rules"]
    if not isinstance(merged_group, dict):
        merged_group = base["command_rules"]
    merged["command_rules"] = {**merged_group, "rules": rules}
    return merged


def merge_local_overrides(base: dict[str, Any], overrides: str | dict[str, Any]) -> dict[str, Any]:
    """A caller-supplied overrides document merged onto a baseline tree as a local layer.

    Accepts YAML text or a JSON mapping for the hook API's `settings_overrides`,
    shared so the SDK's local pre-filter and the server derive the identical
    effective tree. The document merges exactly as a machine's
    `settings.local.yaml` would (`merge_local` semantics, admin
    `permission` locks honored) with one deliberate departure: where a
    machine's stale local file is silently pruned at a locked path, a
    per-request override that changes a locked value is *rejected* —
    `SettingsOverridesError` naming the locked paths — because the caller
    would otherwise enforce under a policy it merely believes is in force. An
    entry that repeats the locked value is accepted (`_changes_only`). Unparseable or non-mapping
    documents raise it too, as does one whose merge produces a schema-invalid
    tree (a bad enum, an unorderable threshold pair, a non-numeric threshold):
    where a machine's boot path *repairs* an invalid merged tree because the
    machine must come up, a per-request override is refused with the offending
    paths — silently falling back to defaults would be the same
    believed-but-not-in-force policy the lock rejection exists to prevent. A
    malformed `command_rules.rules` entry (a non-mapping item, or a rule
    without a string `id`) is refused the same way: the rule merge keys on
    `id` and would silently discard such an entry, leaving the caller
    believing a rule is in force that never merged. So is an override-touched
    rule whose merged form the rule projection would drop (e.g. a new rule
    missing `category`) — see `_reject_unprojectable_override_rules`.
    The document is first canonicalized (`unwrap_composite_wrappers`) so
    every one of these checks and the merge see one shape: a `{value: ...}`
    wrapper around a mapping or list cannot carry a rule past them. An empty
    document returns the baseline unchanged.
    """
    if isinstance(overrides, str):
        try:
            data = load_settings_yaml(overrides)
        except YAMLError as e:
            raise SettingsOverridesError(f"settings_overrides is not parseable YAML: {yaml_error_summary(e)}") from e
    else:
        data = overrides
    if data is None:
        return base
    if not isinstance(data, dict):
        raise SettingsOverridesError("settings_overrides must be a YAML or JSON mapping")
    data = unwrap_composite_wrappers(data)
    _reject_unmergeable_override_rules(data)
    changes = _changes_only(base, data)
    # Nothing left to change asks for nothing locked, even under a root lock.
    locked = locked_override_paths(base, changes) if changes else []
    if locked:
        paths = ", ".join(sorted(set(locked)))
        raise SettingsOverridesError(f"settings_overrides changes admin-locked settings: {paths}")
    merged = merge_local(base, data)
    try:
        WatcherSettings.model_validate(merged)
    except ValidationError as e:
        raise SettingsOverridesError(
            f"settings_overrides produces an invalid settings tree: {validation_error_summary(e)}"
        ) from e
    _reject_unprojectable_override_rules(data, merged)
    return merged


def _changes_only(base: Any, overlay: Any) -> Any:
    """``overlay`` without the entries that already hold ``base``'s value, so only real changes meet the locks.

    An override that repeats a locked value asks for nothing the administrator
    locked: a machine in observe mode restates the mode it runs in, which a
    server locking observe would otherwise refuse. Mappings are compared key
    by key, rule lists rule by rule (`_changed_rules`) and anything else
    whole; ``permission`` keys are dropped, as the merge ignores them. Returns
    an empty mapping when nothing changes.
    """
    if not (_is_mapping(overlay) and _is_mapping(base)):
        return overlay
    changed: dict[str, Any] = {}
    for key, value in overlay.items():
        if key == "permission":
            continue
        if key not in base:
            changed[key] = value
        elif not _same_value(value, base[key]):
            if key == "rules" and is_rule_list(base[key]) and isinstance(value, list):
                # Rules merge by id, so each is narrowed against the base rule
                # with its id, as the lock check reads them.
                rules = _changed_rules(base[key], value)
                if rules:
                    changed[key] = rules
                continue
            narrowed = _changes_only(base[key], value)
            # A partial mapping can differ from the whole base node yet change
            # none of the keys it names.
            if not (_is_mapping(value) and narrowed == {}):
                changed[key] = narrowed
    return changed


def _same_value(overlay: Any, base: Any) -> bool:
    """Whether two settings values are equal as JSON once permissions are stripped.

    Compared as JSON, not with Python equality, so ``true`` never equals ``1``
    and a value of the wrong type still counts as a change. A value JSON cannot
    represent or order (a YAML date, mixed key types) counts as a change too, so
    validation or the lock check sees it rather than its text passing for the
    base's string.
    """
    try:
        return json.dumps(strip_permissions(overlay), sort_keys=True) == json.dumps(
            strip_permissions(base), sort_keys=True
        )
    except (TypeError, ValueError):
        return False


def _changed_rules(base_rules: list[Any], overlay_rules: list[Any]) -> list[Any]:
    """``overlay_rules`` narrowed to what each changes in the base rule with its id.

    A rule that changes nothing is dropped, and one that changes some fields
    keeps only those and its id, so a field it repeats is not read as a change
    to a locked field. A rule with no base counterpart, or no string id, is
    kept whole.
    """
    by_id = {rule["id"]: rule for rule in base_rules if isinstance(rule, dict) and isinstance(rule.get("id"), str)}
    changed: list[Any] = []
    for rule in overlay_rules:
        rule_id = rule.get("id") if isinstance(rule, dict) else None
        if not isinstance(rule_id, str) or rule_id not in by_id:
            changed.append(rule)
            continue
        narrowed = _changes_only(by_id[rule_id], rule)
        if narrowed:
            changed.append({**narrowed, "id": rule_id})
    return changed


def _is_mapping(node: Any) -> bool:
    """A settings mapping, not a ``{value: ...}`` leaf."""
    return isinstance(node, dict) and not is_setting_value(node)


def effective_raw(
    local_scope: LocalSettingsScope,
    admin_path: Path,
    local_path: Path,
    load_builtin_settings: Callable[[], dict[str, Any]],
    ensure_local_imported: Callable[[], None],
    raw_cache: dict[tuple[LocalSettingsScope, SettingsCacheKey], dict[str, Any]],
    load_issues_cache: dict[tuple[LocalSettingsScope, SettingsCacheKey], list[SettingsLoadIssue]],
    applied_overlays: list[AppliedOverlay] | None = None,
) -> dict[str, Any]:
    """The builtin, administrator, local and active-profile layers merged into one settings tree.

    ``local_scope`` picks which machine-local layers apply: none, only the
    global local file, or that file plus the active profile's local entry and
    file. Results are cached in ``raw_cache`` (and the load issues in
    ``load_issues_cache``) on the files' fingerprints. When
    ``applied_overlays`` is given, every layer above the administrator
    baseline is appended to it in merge order (see `AppliedOverlay`); the
    cache is then bypassed, since a cached tree records no layers.
    """
    ensure_local_imported()

    builtin = load_builtin_settings()
    validate_settings_tree(builtin, "Builtin watcher settings")
    issues: list[SettingsLoadIssue] = []
    admin = load_admin_settings(admin_path, issues)
    _report_retired_admin_profile_files(admin_path, issues)
    admin = sanitize_overlay(builtin, admin, "admin", admin_path, issues, merge_admin)
    baseline_admin = merge_admin(builtin, admin)
    local_written = load_local_settings(local_path, issues)
    local = sanitize_overlay(
        baseline_admin,
        local_written,
        "local",
        local_path,
        issues,
        merge_admin,
    )
    metadata_root = merge_local(baseline_admin, local)
    active_profile_id = resolve_active_profile_id(metadata_root, local_path, issues)

    cache_key = (local_scope, settings_cache_key(admin_path, local_path, active_profile_id))
    cached = raw_cache.get(cache_key)
    if cached is not None and applied_overlays is None:
        return cached

    merged = baseline_admin
    if local_scope in ("global", "all"):
        if applied_overlays is not None:
            applied_overlays.append(AppliedOverlay(merged, local_written, local, merge_local))
        merged = merge_local(merged, local)
    if active_profile_id != DEFAULT_PROFILE_ID:
        merged = apply_profile_layers(
            merged,
            baseline_admin,
            active_profile_id,
            admin_path,
            local_path,
            local_scope,
            issues,
            builtin_doc=builtin,
            admin_doc=admin,
            local_doc=local,
            applied_overlays=applied_overlays,
        )
    merged = repair_settings_tree(merged, baseline_admin, "local", local_path, issues)
    raw_cache[cache_key] = merged
    load_issues_cache[cache_key] = issues
    return merged


def settings_cache_key(
    admin_path: Path, local_path: Path, active_profile_id: str = DEFAULT_PROFILE_ID
) -> SettingsCacheKey:
    profile_paths: tuple[Path, ...] = ()
    if active_profile_id != DEFAULT_PROFILE_ID:
        profile_paths = (local_profile_path(local_path, active_profile_id),)
    # Retired organization profile files carry no settings, but they do carry a
    # load issue (see _report_retired_admin_profile_files), and the issues cache
    # shares this key — so their appearance and removal must invalidate it or
    # the warning lags the filesystem until an unrelated file changes.
    retired_paths = _retired_admin_profile_files(admin_path)
    fingerprints = (
        (str(admin_path), path_fingerprint(admin_path)),
        (str(local_path), path_fingerprint(local_path)),
        *((str(path), path_fingerprint(path)) for path in (*profile_paths, *retired_paths)),
    )
    return active_profile_id, fingerprints


def path_fingerprint(path: Path) -> tuple[int, int] | None:
    try:
        stat = path.stat()
    except FileNotFoundError:
        return None
    return stat.st_mtime_ns, stat.st_size


def load_builtin_settings(resource_name: str) -> dict[str, Any]:
    resource = files("watcher_sdk.settings_schema").joinpath(resource_name)
    data = load_settings_yaml(resource.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Builtin watcher settings must be a mapping: {resource}")
    return data


@lru_cache(maxsize=1)
def builtin_settings_digest() -> str:
    """A short fingerprint of the packaged builtin settings document this package ships.

    An org's effective policy is its managed-settings document merged onto
    these builtins, and the two sides of a split decision (a client's local
    deterministic stage, the server's graded stages) each load the builtins
    from their own installed package. The document's own version says nothing
    about the builtins beneath it, so a policy token that carried only the
    version would let a client running older packaged rules skip a rule the
    server's package added. This digest rides along in the token so the server
    can tell the two builtin documents apart. Cached: the packaged document
    never changes within a process.
    """
    text = files("watcher_sdk.settings_schema").joinpath("settings.yaml").read_text(encoding="utf-8")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def list_builtin_profile_ids() -> set[str]:
    """Profile ids Watcher ships, read from the packaged document's own catalog."""
    return profile_ids_from_catalog(load_builtin_settings("settings.yaml").get("profiles"))


def local_profile_path(local_path: Path, profile_id: str) -> Path:
    return local_path.with_name(f"settings.{profile_id}.local.yaml")


# deprecated(0.16.0): the organization profile file (``settings.<id>.yaml``
# beside the admin document). Its reader is gone, so a file that used to
# configure a profile is now inert; this scan turns that silence into a load
# issue naming the migration target. Deliberately kept past the ±1-minor
# window, so do NOT delete this on the release-cut version rule: a machine
# provisioned during a pilot that began before 0.26 can jump straight to a
# current release and would otherwise lose the file's profile settings with
# no signal. Remove once every pilot that started before 0.26 has upgraded
# or concluded (see #9823 / #9848).
_RETIRED_ADMIN_PROFILE_FILE_PATTERN = re.compile(r"settings\.([a-z0-9][a-z0-9_-]*)\.yaml")


def _retired_admin_profile_files(admin_path: Path) -> list[Path]:
    """Organization ``settings.<id>.yaml`` files beside the admin document."""
    matches: list[Path] = []
    for path in sorted(admin_path.parent.glob("settings.*.yaml")):
        if path.name.endswith(".local.yaml"):
            continue
        match = _RETIRED_ADMIN_PROFILE_FILE_PATTERN.fullmatch(path.name)
        if match is None or match.group(1) == "local":
            continue
        matches.append(path)
    return matches


def _report_retired_admin_profile_files(admin_path: Path, issues: list[SettingsLoadIssue]) -> None:
    """Flag organization profile files that no release since 0.26 reads."""
    for path in _retired_admin_profile_files(admin_path):
        profile_id = path.name.removeprefix("settings.").removesuffix(".yaml")
        add_settings_load_issue(
            issues,
            "admin",
            path,
            ("profiles", profile_id),
            f"{path.name} is no longer read. Move its contents into the "
            f"'{profile_id}' entry under 'profiles' in settings.yaml, then delete the file.",
        )


def profile_id_from_builtin_resource(name: str) -> str | None:
    match = re.fullmatch(r"settings\.([a-z0-9][a-z0-9_-]*)\.yaml", name)
    if match is None:
        return None
    profile_id = match.group(1)
    if profile_id == "local":
        return None
    return profile_id


def profile_id_from_local_path(path: Path) -> str | None:
    match = re.fullmatch(r"settings\.([a-z0-9][a-z0-9_-]*)\.local\.yaml", path.name)
    return match.group(1) if match is not None else None


def is_valid_profile_id(profile_id: str) -> bool:
    if profile_id == "local":
        return False
    return PROFILE_ID_PATTERN.fullmatch(profile_id) is not None


def apply_profile_layers(
    merged: dict[str, Any],
    baseline_admin: dict[str, Any],
    profile_id: str,
    admin_path: Path,
    local_path: Path,
    local_scope: LocalSettingsScope,
    issues: list[SettingsLoadIssue],
    builtin_doc: dict[str, Any],
    admin_doc: dict[str, Any],
    local_doc: dict[str, Any],
    applied_overlays: list[AppliedOverlay] | None = None,
) -> dict[str, Any]:
    """Layer the active profile's overrides onto the merged baseline+local tree.

    The overlays are applied in layer order: builtin inline entry, admin inline
    entry, and (when ``local_scope`` includes profile-local state) local inline
    entry, local profile file. Within the local layer the document's inline
    catalog entry comes first, so a separate ``settings.<id>.local.yaml`` file
    wins where the two overlap.

    Inline entries are read from each source document's own ``profiles`` catalog
    (``builtin_doc``, ``admin_doc``, ``local_doc``, the sanitized documents the
    caller loaded) rather than from the merged tree. That way each overlay is
    applied with its own layer's merge semantics and permission root. It also keeps
    the shipped profiles intact when an admin locks the catalog, since a locked
    catalog replaces the builtin one in the merged tree.

    Each overlay applied is appended to ``applied_overlays`` when given (see
    `AppliedOverlay`).
    """

    def merge_admin_layer(base: Any, overlay: Any) -> Any:
        return merge_profile_admin(base, overlay, baseline_admin)

    def apply(
        base: dict[str, Any], written: dict[str, Any], overlay: dict[str, Any], merge: Callable[[Any, Any], Any]
    ) -> dict[str, Any]:
        if applied_overlays is not None:
            applied_overlays.append(AppliedOverlay(base, written, overlay, merge))
        return merge(base, overlay)

    builtin_inline = inline_profile_overlay(builtin_doc, profile_id)
    if builtin_inline:
        merged = apply(merged, builtin_inline, builtin_inline, merge_admin_layer)
        merged = repair_settings_tree(merged, baseline_admin, "local", local_path, issues)

    admin_inline = sanitize_inline_profile_overlay(
        merged,
        admin_doc,
        profile_id,
        "admin",
        admin_path,
        issues,
        merge_admin_layer,
    )
    merged = apply(merged, inline_profile_overlay(admin_doc, profile_id), admin_inline, merge_admin_layer)

    if local_scope == "all":
        local_inline = sanitize_inline_profile_overlay(
            merged,
            local_doc,
            profile_id,
            "local",
            local_path,
            issues,
            merge_profile_local,
        )
        merged = apply(merged, inline_profile_overlay(local_doc, profile_id), local_inline, merge_profile_local)

        # Unlike the retired organization profile file, this one is still written by
        # Watcher every time a setting changes while a non-default profile is active. It
        # can only go once those writes land in the local document's own catalog entry.
        merged = _apply_profile_file(
            merged,
            local_profile_path(local_path, profile_id),
            load_local_settings,
            "local",
            issues,
            merge_profile_local,
            applied_overlays,
        )
    return merged


def _apply_profile_file(
    merged: dict[str, Any],
    path: Path,
    load: Callable[[Path, list[SettingsLoadIssue]], dict[str, Any]],
    source: SettingsSource,
    issues: list[SettingsLoadIssue],
    merge: Callable[[Any, Any], Any],
    applied_overlays: list[AppliedOverlay] | None,
) -> dict[str, Any]:
    """Layer one separate ``settings.<id>`` profile file on, or leave the tree alone.

    A profile file must never stop a machine reading its settings. Anything that goes
    wrong is recorded as a load issue and the tree carries on without the file,
    leaving the machine on what the main document says. Loading and pruning already
    tolerate a missing or malformed file; the guard is for the merge, where a shape
    no current code anticipates could still raise.
    """
    try:
        written = load(path, issues)
        overlay = sanitize_overlay(merged, written, source, path, issues, merge)
        result = merge(merged, overlay)
    except Exception as error:  # noqa: BLE001 - a deprecated profile file must not fail the load
        add_settings_load_issue(
            issues,
            source,
            path,
            None,
            f"This profile file could not be applied and was ignored ({error}). "
            "Move its contents into the profiles entry in settings.yaml.",
        )
        return merged
    if applied_overlays is not None:
        applied_overlays.append(AppliedOverlay(merged, written, overlay, merge))
    return result


# Keys of a profile catalog entry that mark up the entry itself rather than
# carrying overlay content. `permission` governs who may edit the entry, and
# `content_permission` governs everything the entry configures; every other key
# (including name/description/aliases, which double as the profile's display
# metadata) merges into the effective tree like a profile-file key.
INLINE_PROFILE_RESERVED_KEYS = frozenset({"permission", "content_permission"})

# The entry key that plays the role a profile file's top-level `permission` plays.
# An entry needs a separate name for it because `permission` on an entry already
# means something else, namely who may edit the catalog entry.
INLINE_PROFILE_CONTENT_PERMISSION_KEY = "content_permission"


def inline_profile_overlay(source_doc: dict[str, Any], profile_id: str) -> dict[str, Any]:
    """Extract the inline overlay one source document's ``profiles`` catalog carries for a profile.

    Returns ``{}`` when the document has no catalog, no entry for ``profile_id``, or an
    entry with no overlay content (empty, or carrying only the entry's own markup).

    An entry's ``content_permission`` comes back as the overlay's top-level
    ``permission``, which is the shape a separate profile file uses to lock or open
    everything it sets. Rewriting it here means the merge, the permission engine, and
    every caller downstream see one representation and need no special case.
    """
    profiles = source_doc.get("profiles")
    if not isinstance(profiles, dict):
        return {}
    entry = profiles.get(profile_id)
    if not isinstance(entry, dict):
        return {}
    overlay = {key: value for key, value in entry.items() if key not in INLINE_PROFILE_RESERVED_KEYS}
    if not overlay:
        return {}
    content_permission = entry.get(INLINE_PROFILE_CONTENT_PERMISSION_KEY)
    if content_permission is not None:
        overlay["permission"] = content_permission
    return overlay


def sanitize_inline_profile_overlay(
    base: dict[str, Any],
    source_doc: dict[str, Any],
    profile_id: str,
    source: SettingsSource,
    source_path: Path,
    issues: list[SettingsLoadIssue],
    merge: Callable[[Any, Any], Any],
) -> dict[str, Any]:
    """Sanitize one document's inline overlay for a profile, like a profile file's content.

    Inline content is only shallowly validated when the enclosing document loads
    (see ``ProfileCatalogEntry``), so deep-invalid values are pruned here, at apply
    time, against the tree the overlay merges onto. Issue paths are re-prefixed with
    ``profiles.<id>`` so a diagnostic points at the entry inside the source document
    rather than at a top-level key that document does not have.
    """
    overlay = inline_profile_overlay(source_doc, profile_id)
    if not overlay:
        return {}
    inline_issues: list[SettingsLoadIssue] = []
    sanitized = sanitize_overlay(base, overlay, source, source_path, inline_issues, merge)
    prefix = f"profiles.{profile_id}"
    for issue in inline_issues:
        setting_path = f"{prefix}.{issue.setting_path}" if issue.setting_path else prefix
        issues.append(issue.model_copy(update={"setting_path": setting_path}))
    return sanitized


def inline_profile_ids(source_doc: dict[str, Any]) -> set[str]:
    """Profile ids whose catalog entry in ``source_doc`` carries inline overlay content."""
    return {
        profile_id
        for profile_id in profile_ids_from_catalog(source_doc.get("profiles"))
        if inline_profile_overlay(source_doc, profile_id)
    }


def merged_inline_profile_tree(
    builtin: dict[str, Any],
    admin_doc: dict[str, Any],
    profile_id: str,
) -> dict[str, Any]:
    """Simulate the admin-layer merge for one profile of an admin document.

    Applies, onto the builtin+admin baseline, the builtin inline entry and then the
    admin document's inline entry, in the same order and with the same merge semantics
    a client uses for the admin layers of an active profile. The result is what a
    machine with this admin document and this profile active would run (before any
    machine-local files), so server-side checks can validate exactly what will be
    applied fleet-wide.
    """
    baseline = merge_admin(builtin, admin_doc)
    merged = baseline
    builtin_inline = inline_profile_overlay(builtin, profile_id)
    if builtin_inline:
        merged = merge_profile_admin(merged, builtin_inline, baseline)
    return merge_profile_admin(merged, inline_profile_overlay(admin_doc, profile_id), baseline)


def repaired_inline_profile_tree(
    builtin: dict[str, Any],
    admin_doc: dict[str, Any],
    profile_id: str,
) -> dict[str, Any]:
    """The profile's tree with everything but the entry's own contribution already sound.

    :func:`merged_inline_profile_tree` reproduces the merge faithfully, which means
    it also reproduces any collision the document's top level already had with the
    shipped builtin overlay. A machine repairs that on load, so a caller wanting to
    judge the entry alone needs the same starting point: build the profile without
    the entry's content, repair it the way a client does, then apply the entry.
    Whatever is wrong with the result is the entry's doing.

    Both checks a distributable document gets, schema validity and command-rule
    regex compilability, must run against this one tree. Judging them against
    different trees lets a repairable collision in the first hide a real fault the
    second would have caught.
    """
    baseline = merge_admin(builtin, admin_doc)
    repaired = repair_settings_tree(
        merged_inline_profile_tree(builtin, _without_inline_entry(admin_doc, profile_id), profile_id),
        baseline,
        "admin",
        Path("settings.yaml"),
        [],
    )
    return merge_profile_admin(repaired, inline_profile_overlay(admin_doc, profile_id), baseline)


def inline_profile_validation_error(
    builtin: dict[str, Any],
    admin_doc: dict[str, Any],
    profile_id: str,
) -> str | None:
    """Validate one profile's inline overlay as an admin-layer client will apply it.

    The enclosing document only validates inline entries shallowly (see
    ``ProfileCatalogEntry``), so a distributable document needs this deeper check.
    It validates the tree from :func:`repaired_inline_profile_tree` and returns a
    ``profiles.<id>``-prefixed error summary, or None when the profile applies
    cleanly. The server calls it before accepting a managed settings document and
    the client before writing a pulled one, so a document whose inline content would
    be pruned fleet-wide is rejected up front instead of degrading silently.

    Only failures the inline entry introduces are reported. A document whose own top
    level already collides with the shipped builtin profile overlay (say a locked low
    deny threshold under a builtin profile that raises the flag threshold) is invalid
    with or without the entry, and rejecting it for that would blame values the author
    never wrote. Repairing first is what draws the line, rather than trying to spot
    the pre-existing failure in the final error list. An entry that breaks the very
    setting the baseline already broke reports the same path and the same message, so
    comparing errors would wave through the case that matters most.
    """
    try:
        WatcherSettings.model_validate(repaired_inline_profile_tree(builtin, admin_doc, profile_id))
    except ValidationError as e:
        return f"profiles.{profile_id}: {validation_error_summary(e)}"
    return None


def _without_inline_entry(admin_doc: dict[str, Any], profile_id: str) -> dict[str, Any]:
    """A copy of ``admin_doc`` with the profile's entry reduced to its catalog markup."""
    profiles = dict(admin_doc.get("profiles") or {})
    entry = profiles.get(profile_id)
    if isinstance(entry, dict):
        profiles[profile_id] = {"permission": entry["permission"]} if "permission" in entry else {}
    return {**admin_doc, "profiles": profiles}


def resolve_active_profile_id(
    metadata_root: dict[str, Any],
    local_path: Path,
    issues: list[SettingsLoadIssue],
) -> str:
    available_profiles = available_profile_ids(metadata_root, local_path)
    fallback_profile_id = fallback_active_profile_id(available_profiles)
    # active_profile may carry the {value, permission} wrapper (admins pin the
    # profile with permission: locked), so unwrap before interpreting it.
    raw_profile_id = unwrap(metadata_root.get("active_profile"))
    if raw_profile_id is None:
        return fallback_profile_id
    if isinstance(raw_profile_id, str):
        if raw_profile_id in available_profiles:
            return raw_profile_id
        # A pinned profile has to mean one thing on every machine, and only an id is
        # certain to: a machine's available profiles include whatever its developer
        # wrote, so a developer could otherwise create a profile named for the alias
        # in the pin and have the machine run that instead. Aliases are matched only
        # where the profile was already the developer's to choose.
        if node_permission(metadata_root.get("active_profile")) != "locked":
            aliased_profile_id = resolve_profile_alias(metadata_root, raw_profile_id, available_profiles)
            if aliased_profile_id is not None:
                return aliased_profile_id
    if not isinstance(raw_profile_id, str) or not is_valid_profile_id(raw_profile_id):
        add_settings_load_issue(
            issues,
            "local",
            local_path,
            ("active_profile",),
            f"Active profile must be a valid profile id; using {fallback_profile_id!r}",
        )
        return fallback_profile_id
    add_settings_load_issue(
        issues,
        "local",
        local_path,
        ("active_profile",),
        f"Active profile {raw_profile_id!r} is not available; using {fallback_profile_id!r}",
    )
    return fallback_profile_id


def resolve_profile_alias(catalog_root: dict[str, Any], name: str, available_profiles: set[str]) -> str | None:
    """The available profile that declares ``name`` as one of its aliases, or None.

    A profile can declare ``aliases`` beside its display name, and those names work
    wherever a person names a profile, not only in the CLI's matcher. So
    ``active_profile: human-in-the-loop`` selects the profile that typing the same name at
    the CLI selects.

    An alias only reaches a profile in ``available_profiles``, so it cannot select a profile
    that an admin's locked catalog leaves out. An alias two available profiles both declare
    resolves to neither: picking one would be arbitrary, and every machine has to make the
    same choice.

    ``catalog_root`` must already carry every layer whose aliases count, so callers pass a
    merged document rather than a bare overlay. Aliases then follow the same merge rules as
    the rest of the catalog: an admin who replaces a shipped profile's ``aliases`` replaces
    the names that match it here too, exactly as they do for the CLI. The document's own
    top-level ``aliases`` name the default profile, which is the one profile with no catalog
    entry of its own to carry them.

    Only aliases declared in a catalog entry are read. The deprecated separate
    ``settings.<id>.yaml`` profile file can also carry ``aliases``, and those stay matchable
    at the CLI but not from ``active_profile``; reading every profile file on disk would put
    a directory walk on the permission hook's path, for a deprecated file form.

    Comparison is case-insensitive and ignores whitespace differences, the same comparison
    the CLI uses. Profile ids themselves are matched exactly, by the caller, before this is
    consulted, so an alias never lets a mis-cased id through.
    """
    normalized_name = normalize_profile_name(name)
    claimants = {
        profile_id
        for profile_id, aliases in _declared_profile_aliases(catalog_root).items()
        if profile_id in available_profiles and normalized_name in {normalize_profile_name(a) for a in aliases}
    }
    if len(claimants) != 1:
        return None
    return claimants.pop()


def _declared_profile_aliases(source_doc: dict[str, Any]) -> dict[str, list[str]]:
    """The aliases one settings document declares, keyed by the profile id that declares them."""
    profiles = source_doc.get("profiles")
    declared = (
        {
            profile_id: _alias_list(entry.get("aliases"))
            for profile_id, entry in profiles.items()
            if is_valid_profile_id(profile_id) and isinstance(entry, dict)
        }
        if isinstance(profiles, dict)
        else {}
    )
    # The default profile is the document's own top level, so its names live there and
    # not in the catalog. The catalog's `default` entry exists to carry a permission.
    declared[DEFAULT_PROFILE_ID] = _alias_list(source_doc.get("aliases"))
    return declared


def _alias_list(node: object) -> list[str]:
    """The alias strings in a catalog entry's ``aliases`` node, which may be anything on disk."""
    if not isinstance(node, list):
        return []
    return [alias for alias in node if isinstance(alias, str) and alias]


def normalize_profile_name(name: str) -> str:
    """Fold a profile id, display name, or alias to the form names are compared in.

    Shared with the CLI's profile matcher so both surfaces accept exactly the same
    spellings of a name.
    """
    return " ".join(name.casefold().strip().split())


def fallback_active_profile_id(available_profiles: set[str]) -> str:
    ordered_profiles = ordered_profile_ids(available_profiles)
    if ordered_profiles:
        return ordered_profiles[0]
    return DEFAULT_PROFILE_ID


def ordered_profile_ids(profile_ids: set[str]) -> list[str]:
    ordered: list[str] = []
    if DEFAULT_PROFILE_ID in profile_ids:
        ordered.append(DEFAULT_PROFILE_ID)
    ordered.extend(sorted(profile_id for profile_id in profile_ids if profile_id != DEFAULT_PROFILE_ID))
    return ordered


def available_profile_ids(metadata_root: dict[str, Any], local_path: Path) -> set[str]:
    profiles = metadata_root.get("profiles")
    catalog_ids = profile_ids_from_catalog(profiles)
    if node_permission(profiles) == "locked":
        return catalog_ids
    return catalog_ids | list_builtin_profile_ids() | list_local_profile_ids(local_path) | {DEFAULT_PROFILE_ID}


def distributable_profile_ids(admin_doc: dict[str, Any]) -> set[str]:
    """Profiles a machine holding this document alone could end up running.

    The server-side counterpart to :func:`available_profile_ids`, which needs a
    machine's filesystem to see its local catalog and any per-profile files. A
    distributed document cannot see those, so this is what follows from the document
    plus what Watcher ships: the document's catalog ids, the builtin profiles, and
    ``default``. A machine may offer more than this, never fewer.

    A locked catalog replaces the builtin one wholesale, so then the document's ids
    are the whole list.
    """
    profiles = admin_doc.get("profiles")
    catalog_ids = profile_ids_from_catalog(profiles)
    if node_permission(profiles) == "locked":
        return catalog_ids
    return catalog_ids | list_builtin_profile_ids() | {DEFAULT_PROFILE_ID}


def profile_ids_from_catalog(profiles: object) -> set[str]:
    if not isinstance(profiles, dict):
        return set()
    return {
        key
        for key, value in profiles.items()
        if key != "permission" and is_valid_profile_id(key) and isinstance(value, dict)
    }


def list_local_profile_ids(local_path: Path) -> set[str]:
    result: set[str] = set()
    for path in local_path.parent.glob("settings.*.local.yaml"):
        profile_id = profile_id_from_local_path(path)
        if profile_id is not None:
            result.add(profile_id)
    return result


def load_admin_settings(path: Path, issues: list[SettingsLoadIssue]) -> dict[str, Any]:
    return load_yaml_path_lenient(path, "admin", issues)


def load_local_settings(path: Path, issues: list[SettingsLoadIssue]) -> dict[str, Any]:
    return drop_derived_local_settings(load_yaml_path_lenient(path, "local", issues))


def load_local_settings_for_write(path: Path) -> dict[str, Any]:
    try:
        return drop_derived_local_settings(load_yaml_path_strict(path))
    except ValueError as e:
        raise ValueError(
            f"Cannot update {path} because it is not parseable. "
            "Fix or delete the file and try again. "
            f"Original error: {e}"
        ) from e


def load_yaml_path_lenient(path: Path, source: SettingsSource, issues: list[SettingsLoadIssue]) -> dict[str, Any]:
    try:
        return load_yaml_path_strict(path)
    except ValueError as e:
        message = f"{settings_file_error_message(path, e)}. This file was ignored."
        add_settings_load_issue(issues, source, path, None, message)
        return {}


def load_yaml_path_strict(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = load_settings_yaml(path.read_text(encoding="utf-8"))
    except YAMLError as e:
        raise ValueError(f"{path} could not be parsed: {yaml_error_summary(e)}") from e
    except (OSError, UnicodeDecodeError) as e:
        raise ValueError(f"{path} could not be read: {e}") from e
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ValueError(f"Watcher settings file must contain a mapping: {path}")
    return data


def prune_locked_local(
    local: dict[str, Any],
    admin_path: Path,
    load_builtin_settings: Callable[[], dict[str, Any]],
) -> dict[str, Any]:
    issues: list[SettingsLoadIssue] = []
    builtin = load_builtin_settings()
    validate_settings_tree(builtin, "Builtin watcher settings")
    admin = sanitize_overlay(builtin, load_admin_settings(admin_path, issues), "admin", admin_path, issues, merge_admin)
    base = merge_admin(builtin, admin)
    if node_permission(base) == "locked":
        return {}
    diff = diff_against_base(base, local)
    if diff is NO_DIFF or not isinstance(diff, dict):
        return {}
    return diff


def settings_file_error_message(path: Path, error: ValueError) -> str:
    message = str(error)
    for prefix in (f"{path} ", f"{path}: "):
        if message.startswith(prefix):
            return message.removeprefix(prefix)
    return message


def yaml_error_summary(error: YAMLError) -> str:
    problem = getattr(error, "problem", None)
    mark = getattr(error, "problem_mark", None)
    line = getattr(mark, "line", None)
    column = getattr(mark, "column", None)
    if isinstance(line, int) and isinstance(column, int):
        location = f"line {line + 1}, column {column + 1}"
        if isinstance(problem, str) and problem:
            return f"{problem} ({location})"
        return f"invalid YAML ({location})"
    first_line = str(error).splitlines()[0] if str(error).splitlines() else "invalid YAML"
    return first_line
